#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import io
import asyncio
import logging
import threading
import tempfile
from fractions import Fraction
from time import monotonic

import numpy as np
import av
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack

from dotenv import load_dotenv
from gtts import gTTS
try:
    import pyttsx3  # optional offline fallback
except Exception:
    pyttsx3 = None

# --- Roboflow Inference SDK ---
from inference_sdk import InferenceHTTPClient

# ================== Config ==================
load_dotenv()
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000"]}})

# --- Free TTS endpoint config (no token required) ---
FREE_TTS_PROVIDER = os.getenv("FREE_TTS_PROVIDER", "gtts").lower()   # 'gtts' (online) or 'pyttsx3' (offline)
FREE_TTS_LANG     = os.getenv("FREE_TTS_LANG", "en").strip()
FREE_TTS_SLOW     = os.getenv("FREE_TTS_SLOW", "0").strip().lower() in ("1", "true", "yes", "on")

# --- Roboflow (required) ---
ROBOFLOW_API_KEY    = os.getenv("ROBOFLOW_API_KEY", "").strip()
ROBOFLOW_WORKSPACE  = os.getenv("ROBOFLOW_WORKSPACE", "hackvt25").strip()
ROBOFLOW_WORKFLOWID = os.getenv("ROBOFLOW_WORKFLOW_ID", "custom-workflow-10").strip()

# --- Realtime / pacing ---
SAMPLE_RATE   = 48000        # Hz
FRAME_MS      = 20           # ms per Opus frame
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 960
CHANNELS      = 1

# --- Video sampling (infer every N frames) ---
FRAME_SKIP_FRAMES = int(os.getenv("FRAME_SKIP_FRAMES", "0"))   # 0 = disabled; >0 = fixed skip
FRAME_SKIP_RATIO  = int(os.getenv("FRAME_SKIP_RATIO", "4"))    # infer ~fps/4 if FRAME_SKIP_FRAMES=0
CONFIDENCE_MIN    = float(os.getenv("CONFIDENCE_MIN", "0.50"))

# --- Stabilization of recognized tokens ---
STREAK_MIN       = int(os.getenv("STREAK_MIN", "3"))         # >= N repeats to accept a word
WORD_COOLDOWN_S  = float(os.getenv("WORD_COOLDOWN_S", "1.2"))

# --- Optional batching before sending to client TTS ---
BATCH_TIMEOUT_S  = float(os.getenv("BATCH_TIMEOUT_S", "0.6"))

# --- Exclude exact junk labels you observed locally ---
EXCLUDE_EXACT = set(s.strip().lower() for s in os.getenv(
    "EXCLUDE_EXACT", "1,1 0 0 1 0 1 1 0 1,your"
).split(",") if s.strip())

# Dedicated asyncio loop (Flask is sync)
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()

# Keep sessions
SESSIONS = {}  # id(pc) -> {"pc": pc, "emitter": TextChannelEmitter, "video_task": task}


# ================== TTS helpers for /tts endpoint ==================

def _gtts_bytes(text: str) -> bytes:
    buf = io.BytesIO()
    gTTS(text=text, lang=FREE_TTS_LANG or "en", slow=FREE_TTS_SLOW).write_to_fp(buf)
    return buf.getvalue()

def _pyttsx3_bytes(text: str) -> bytes:
    if pyttsx3 is None:
        raise RuntimeError("pyttsx3 is not installed; set FREE_TTS_PROVIDER=gtts or install pyttsx3")
    with tempfile.TemporaryDirectory() as td:
        wav_path = os.path.join(td, "tts.wav")
        engine = pyttsx3.init()
        engine.save_to_file(text, wav_path)
        engine.runAndWait()
        with open(wav_path, "rb") as f:
            return f.read()

def _free_tts_bytes(text: str) -> bytes:
    return _pyttsx3_bytes(text) if FREE_TTS_PROVIDER == "pyttsx3" else _gtts_bytes(text)


# ================== Text emitter over DataChannel ==================

class TextChannelEmitter:
    """Batches tokens, then sends phrase strings over a DataChannel."""
    def __init__(self):
        self.channel = None
        self._batch = []
        self._last_token_time = 0.0

    def attach(self, channel):
        self.channel = channel

    def _send_phrase(self, phrase: str):
        ch = self.channel
        if not ch:
            return
        # aiortc RTCDataChannel has .readyState
        try:
            if getattr(ch, "readyState", "open") == "open":
                ch.send(phrase)
        except Exception:
            logging.exception("DataChannel send failed")

    def add_token(self, token: str):
        token = (token or "").strip()
        if not token:
            return
        now = monotonic()
        self._batch.append(token)
        self._last_token_time = now

        async def _await_idle_and_flush(last_time=now):
            await asyncio.sleep(BATCH_TIMEOUT_S)
            if self._last_token_time == last_time and self._batch:
                phrase = " ".join(self._batch)
                self._batch.clear()
                self._send_phrase(phrase)

        asyncio.ensure_future(_await_idle_and_flush())


# ================== Sign Recognition from inbound video ==================

class RoboflowSignRecognizer:
    """
    Runs a Roboflow workflow on sampled frames (raw + horizontally flipped).
    Emits the highest-confidence label above CONFIDENCE_MIN.
    Uses a 'streak' and cooldown to stabilize before sending.
    """
    def __init__(self):
        if not ROBOFLOW_API_KEY:
            raise RuntimeError("ROBOFLOW_API_KEY is not set")

        self.client = InferenceHTTPClient(
            api_url="https://serverless.roboflow.com",
            api_key=ROBOFLOW_API_KEY,
        )
        self.workspace = ROBOFLOW_WORKSPACE
        self.workflow_id = ROBOFLOW_WORKFLOWID

        # Stabilizer state
        self.curr_word = None
        self.streak = 0
        self.last_spoken = ""
        self.cooldown_until = 0.0

    def _iter_candidates(self, wf_result):
        """Yield prediction dicts with 'class' and 'confidence' from a workflow result."""
        try:
            node_map = wf_result[0]
        except Exception:
            return
        for node_key, node_val in node_map.items():
            if node_key == "output":
                continue
            items = node_val if isinstance(node_val, list) else [node_val]
            for item in items:
                preds = item.get("predictions") or []
                if isinstance(preds, list) and preds:
                    yield preds[0]

    def infer_image(self, bgr_image: np.ndarray):
        """Run on original and flipped frames; return (best_class, best_conf) or (None, 0.0)."""
        try:
            res_a = self.client.run_workflow(
                workspace_name=self.workspace,
                workflow_id=self.workflow_id,
                images={"image": bgr_image},
                use_cache=True
            )

            bgr_flipped = bgr_image[:, ::-1, :]
            res_b = self.client.run_workflow(
                workspace_name=self.workspace,
                workflow_id=self.workflow_id,
                images={"image": bgr_flipped},
                use_cache=True
            )

            best_cls, best_conf = None, 0.0

            def consider(pred):
                nonlocal best_cls, best_conf
                cls = (pred.get("class") or "").strip()
                if not cls or cls.lower() in EXCLUDE_EXACT:
                    return
                conf = float(pred.get("confidence") or 0.0)
                if conf >= CONFIDENCE_MIN and conf > best_conf:
                    best_cls, best_conf = cls, conf

            for p in self._iter_candidates(res_a):
                consider(p)
            for p in self._iter_candidates(res_b):
                consider(p)

            if best_cls:
                return best_cls, best_conf
            return None, 0.0

        except Exception as e:
            logging.exception("Roboflow inference failed: %s", e)
            return None, 0.0

    def push_prediction(self, token: str, on_emit):
        """Streak-based stabilizer."""
        now = monotonic()
        if token == self.curr_word:
            self.streak += 1
        else:
            self.curr_word = token
            self.streak = 1

        if self.streak >= STREAK_MIN and token:
            # cooldown on repeats
            if token == self.last_spoken and now < self.cooldown_until:
                return
            self.last_spoken = token
            self.cooldown_until = now + WORD_COOLDOWN_S
            on_emit(token)


async def consume_video_loop(track: MediaStreamTrack, emitter: TextChannelEmitter):
    recognizer = RoboflowSignRecognizer()
    frame_idx = 0
    fps_guess = 24
    frame_skip = FRAME_SKIP_FRAMES if FRAME_SKIP_FRAMES > 0 else max(1, fps_guess // FRAME_SKIP_RATIO)

    logging.info("Video consumer started (frame_skip=%s)", frame_skip)

    try:
        while True:
            vf = await track.recv()  # av.VideoFrame
            frame_idx += 1

            if frame_idx % frame_skip != 0:
                continue

            bgr = vf.to_ndarray(format="bgr24")

            best_cls, best_conf = await loop.run_in_executor(None, recognizer.infer_image, bgr)
            if best_cls:
                def _emit(token):
                    logging.info("Recognized (stabilized): %s (%.2f)", token, best_conf)
                    emitter.add_token(token)
                recognizer.push_prediction(best_cls, on_emit=_emit)

    except asyncio.CancelledError:
        logging.info("Video consumer cancelled")
    except Exception as e:
        logging.exception("Video consumer error: %s", e)
    finally:
        logging.info("Video consumer ended")


# ================== WebRTC offer/answer ==================

async def _wait_ice_complete(pc: RTCPeerConnection, timeout=2.0):
    if pc.iceGatheringState == "complete":
        return
    done = asyncio.Event()

    @pc.on("icegatheringstatechange")
    def _():
        if pc.iceGatheringState == "complete":
            done.set()

    try:
        await asyncio.wait_for(done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass


async def handle_offer(offer_sdp: str, offer_type: str) -> str:
    pc = RTCPeerConnection()
    emitter = TextChannelEmitter()

    @pc.on("iceconnectionstatechange")
    def _():
        logging.info("ICE state: %s", pc.iceConnectionState)

    video_task_holder = {"task": None}

    @pc.on("track")
    def on_track(track):
        logging.info("Inbound track: %s", track.kind)
        if track.kind == "video":
            task = asyncio.ensure_future(consume_video_loop(track, emitter))
            video_task_holder["task"] = task

        @track.on("ended")
        async def _on_ended():
            logging.info("Track %s ended", track.kind)
            if video_task_holder["task"]:
                video_task_holder["task"].cancel()

    @pc.on("datachannel")
    def on_datachannel(channel):
        logging.info("DataChannel created: %s", channel.label)
        if channel.label == "tts-text":
            emitter.attach(channel)

            @channel.on("open")
            def _on_open():
                try:
                    channel.send("Connection established. Sign recognition is live.")
                except Exception:
                    pass

            @channel.on("close")
            def _on_close():
                emitter.attach(None)

    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type=offer_type))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    await _wait_ice_complete(pc, timeout=2.0)

    # Keep strong refs
    SESSIONS[id(pc)] = {"pc": pc, "emitter": emitter, "video_task": video_task_holder["task"]}

    logging.info("Answer created")
    return pc.localDescription.sdp


# ================== Routes ==================

@app.route("/")
def health():
    return "OK", 200


@app.route("/webrtc/offer", methods=["POST"])
def webrtc_offer():
    data = request.get_json(force=True)
    offer_sdp = data.get("sdp")
    offer_type = data.get("type", "offer")
    if not offer_sdp:
        return jsonify({"error": "missing sdp"}), 400

    fut = asyncio.run_coroutine_threadsafe(handle_offer(offer_sdp, offer_type), loop)
    try:
        answer_sdp = fut.result(timeout=15)
        return jsonify({"sdp": answer_sdp, "type": "answer"}), 200
    except Exception as e:
        logging.exception("Failed to create answer")
        return jsonify({"error": str(e)}), 500


@app.get("/tts")
def tts_http():
    """Client-side fetch for audio bytes. Query: /tts?text=Hello%20world"""
    text = (request.args.get("text") or "").strip()
    if not text:
        return "missing text", 400
    try:
        audio_bytes = _free_tts_bytes(text)
        # gTTS returns MP3; pyttsx3 returns WAV bytes – set mimetype accordingly
        mimetype = "audio/mpeg" if FREE_TTS_PROVIDER == "gtts" else "audio/wav"
        return send_file(io.BytesIO(audio_bytes), mimetype=mimetype)
    except Exception as e:
        logging.exception("TTS error: %s", e)
        return "tts failed", 500


@app.route("/shutdown-peers", methods=["POST"])
def shutdown_peers():
    async def _close_all():
        tasks = []
        for k, sess in list(SESSIONS.items()):
            try:
                if sess.get("video_task"):
                    sess["video_task"].cancel()
            except Exception:
                pass
            tasks.append(sess["pc"].close())
            SESSIONS.pop(k, None)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run_coroutine_threadsafe(_close_all(), loop).result(timeout=5)
    return jsonify({"ok": True, "remaining": len(SESSIONS)}), 200


if __name__ == "__main__":
    # keep debug=False so the dev reloader doesn't kill our asyncio loop
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
