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
import requests
from flask import Flask, request, jsonify
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

# --- Free TTS engine (no token required) ---
TTS_ENGINE = os.getenv("TTS_ENGINE", "free").lower()  # keep as 'free'
FREE_TTS_PROVIDER = os.getenv("FREE_TTS_PROVIDER", "gtts").lower()  # 'gtts' (online) or 'pyttsx3' (offline)
FREE_TTS_LANG = os.getenv("FREE_TTS_LANG", "en").strip()
FREE_TTS_SLOW = os.getenv("FREE_TTS_SLOW", "0").strip().lower() in ("1", "true", "yes", "on")

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
FRAME_SKIP_RATIO = int(os.getenv("FRAME_SKIP_RATIO", "4"))  # infer ~fps/4
CONFIDENCE_MIN   = float(os.getenv("CONFIDENCE_MIN", "0.50"))

# --- Stabilization of recognized tokens ---
STREAK_MIN       = int(os.getenv("STREAK_MIN", "3"))         # >= N repeats to accept a word
WORD_COOLDOWN_S  = float(os.getenv("WORD_COOLDOWN_S", "1.2"))

# --- Optional batching to reduce TTS calls ---
BATCH_TIMEOUT_S  = float(os.getenv("BATCH_TIMEOUT_S", "0.6"))

# --- Optional filtering: only consider these node keys / classes ---
SIGN_NODE_KEYS = [s.strip() for s in os.getenv("SIGN_NODE_KEYS", "").split(",") if s.strip()]
ALLOWED_CLASSES = set(s.strip().lower() for s in os.getenv("ALLOWED_CLASSES", "").split(",") if s.strip())
DENY_CLASSES    = set(s.strip().lower() for s in os.getenv("DENY_CLASSES", "person,face,hand").split(",") if s.strip())

# Dedicated asyncio loop (Flask is sync)
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()

# Keep sessions (strong refs)
SESSIONS = {}  # id(pc) -> {"pc": pc, "tts": TTSAudioTrack, "video_task": task}


# ================== TTS helpers (FREE) ==================

def _gtts_bytes(text: str) -> bytes:
    """
    gTTS (no token). Returns MP3 bytes.
    """
    buf = io.BytesIO()
    gTTS(text=text, lang=FREE_TTS_LANG or "en", slow=FREE_TTS_SLOW).write_to_fp(buf)
    return buf.getvalue()

def _pyttsx3_bytes(text: str) -> bytes:
    """
    Offline TTS via Windows SAPI5/mac/nix engines (no token). Returns WAV bytes.
    """
    if pyttsx3 is None:
        raise RuntimeError("pyttsx3 is not installed; set FREE_TTS_PROVIDER=gtts or install pyttsx3")
    with tempfile.TemporaryDirectory() as td:
        wav_path = os.path.join(td, "tts.wav")
        engine = pyttsx3.init()
        # You can tweak voice/rate here if desired:
        # rate = engine.getProperty('rate'); engine.setProperty('rate', rate + 20)
        engine.save_to_file(text, wav_path)
        engine.runAndWait()
        with open(wav_path, "rb") as f:
            return f.read()

def _free_tts_bytes(text: str) -> bytes:
    if FREE_TTS_PROVIDER == "pyttsx3":
        return _pyttsx3_bytes(text)
    # default: gTTS
    return _gtts_bytes(text)

def _decode_audio_to_frames(audio_bytes: bytes):
    """Decode arbitrary audio bytes (mp3/wav) into a list of av.AudioFrame."""
    if not audio_bytes:
        return []
    with av.open(io.BytesIO(audio_bytes), mode="r") as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            return []
        frames = []
        for pkt in container.demux(stream):
            for fr in pkt.decode():
                frames.append(fr)
        return frames

def _slice_to_20ms_i16_mono(fr: av.AudioFrame, resampler: av.AudioResampler):
    """
    Resample to s16/mono/48k and yield 20ms chunks shaped (1, 960) int16.
    """
    out_frames = resampler.resample(fr) or []
    for rf in out_frames:
        arr = rf.to_ndarray(format="s16")  # (C, N) int16
        if arr.ndim == 1:
            arr = arr.reshape(1, -1)
        if arr.shape[0] > 1:
            # mixdown to mono
            arr = np.mean(arr.astype(np.int32), axis=0, keepdims=True).astype(np.int16)
        mono = arr[0]  # (N,)
        i, n = 0, mono.shape[0]
        while i < n:
            j = min(i + FRAME_SAMPLES, n)
            chunk = mono[i:j]
            if chunk.shape[0] < FRAME_SAMPLES:
                pad = np.zeros((FRAME_SAMPLES,), dtype=np.int16)
                pad[:chunk.shape[0]] = chunk
                chunk = pad
            yield chunk.reshape(1, -1)
            i = j

def _silence_chunk():
    return np.zeros((1, FRAME_SAMPLES), dtype=np.int16)


# ================== TTS over WebRTC ==================

class TTSAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self._queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=400)
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        self._batch = []
        self._last_token_time = 0.0
        self._t0 = 0  # running sample index for PTS

    async def recv(self):
        try:
            # try to get a 20ms chunk; if none, send silence
            chunk = await asyncio.wait_for(self._queue.get(), timeout=FRAME_MS / 1000.0)
        except asyncio.TimeoutError:
            chunk = _silence_chunk()

        frame = av.AudioFrame.from_ndarray(chunk, format="s16", layout="mono")
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._t0
        frame.time_base = Fraction(1, SAMPLE_RATE)
        self._t0 += FRAME_SAMPLES

        # tiny sleep to keep CPU sane (aiortc still paces RTP)
        await asyncio.sleep(FRAME_MS / 1000.0)
        return frame

    def enqueue_text(self, text: str):
        """
        Synthesize `text` with FREE TTS and enqueue audio chunks.
        Work is off-thread.
        """
        text = (text or "").strip()
        if not text:
            return

        def _tts_bytes_router(txt: str) -> bytes:
            # only free engines here
            return _free_tts_bytes(txt)

        async def _worker():
            try:
                audio_bytes = await loop.run_in_executor(None, _tts_bytes_router, text)
                frames = await loop.run_in_executor(None, _decode_audio_to_frames, audio_bytes)
                for fr in frames:
                    for chunk in _slice_to_20ms_i16_mono(fr, self._resampler):
                        try:
                            self._queue.put_nowait(chunk)
                        except asyncio.QueueFull:
                            # drop-oldest to stay responsive
                            try:
                                _ = self._queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                            try:
                                self._queue.put_nowait(chunk)
                            except asyncio.QueueFull:
                                pass
            except Exception as e:
                logging.exception("enqueue_text failed: %s", e)

        asyncio.ensure_future(_worker())

    # Tiny batcher (collect multiple short tokens into one TTS call)
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
                self.enqueue_text(phrase)

        asyncio.ensure_future(_await_idle_and_flush())


# ================== Sign Recognition from inbound video ==================

class RoboflowSignRecognizer:
    """
    Runs a Roboflow workflow on sampled video frames to predict a word.
    Applies a simple 'streak' stabilizer so we only emit a token when
    the same class repeats STREAK_MIN times, with a cooldown.
    Also supports node/label filtering to avoid generic 'person' spam.
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

        self.curr_word = None
        self.streak = 0
        self.last_spoken = ""
        self.cooldown_until = 0.0

    def infer_image(self, bgr_image: np.ndarray):
        """
        Calls Roboflow workflow with a BGR numpy image.
        Returns (best_class, best_conf) or (None, 0.0)
        """
        try:
            result = self.client.run_workflow(
                workspace_name=self.workspace,
                workflow_id=self.workflow_id,
                images={"image": bgr_image},
                use_cache=True
            )
            # result[0] is a dict of nodes; each node may have 'predictions'
            best_cls, best_conf = None, 0.0
            node_map = result[0]

            # Uncomment once to see available node keys:
            # logging.info("Workflow nodes: %s", list(node_map.keys()))

            for node_key, node in node_map.items():
                if SIGN_NODE_KEYS and node_key not in SIGN_NODE_KEYS:
                    continue  # only use your sign-classifier node(s)

                preds = node.get("predictions") or []
                if not preds:
                    continue

                pred0 = preds[0]
                cls = (pred0.get("class") or "").strip()
                conf = float(pred0.get("confidence", 0.0))
                if not cls:
                    continue

                if conf > best_conf:
                    best_cls, best_conf = cls, conf

            if best_conf >= CONFIDENCE_MIN:
                return best_cls, best_conf
            return None, 0.0
        except Exception as e:
            logging.exception("Roboflow inference failed: %s", e)
            return None, 0.0

    def push_prediction(self, token: str, on_emit):
        """
        Update streak logic and call on_emit(token) when stable.
        """
        now = monotonic()
        if token == self.curr_word:
            self.streak += 1
        else:
            self.curr_word = token
            self.streak = 1

        if self.streak >= STREAK_MIN and token:
            # cooldown to avoid spam of same word
            if token == self.last_spoken and now < self.cooldown_until:
                return
            self.last_spoken = token
            self.cooldown_until = now + WORD_COOLDOWN_S
            on_emit(token)


async def consume_video_loop(track: MediaStreamTrack, tts: TTSAudioTrack):
    """
    Read frames from inbound WebRTC video track, sample every N frames,
    run Roboflow, and push stabilized tokens into the TTS batcher.
    """
    recognizer = RoboflowSignRecognizer()
    frame_idx = 0
    fps_guess = 24  # just for frame skip default if no timing available
    frame_skip = max(1, fps_guess // FRAME_SKIP_RATIO)

    logging.info("Video consumer started (frame_skip=%s)", frame_skip)

    try:
        while True:
            vf = await track.recv()  # av.VideoFrame
            frame_idx += 1

            if frame_idx % frame_skip != 0:
                continue

            # Convert to numpy BGR
            bgr = vf.to_ndarray(format="bgr24")

            # Run inference off-thread (avoid blocking event loop)
            best_cls, best_conf = await loop.run_in_executor(
                None, recognizer.infer_image, bgr
            )
            if best_cls:
                def _emit(token):
                    logging.info("Recognized (stabilized): %s (%.2f)", token, best_conf)
                    tts.add_token(token)
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

    @pc.on("iceconnectionstatechange")
    def _():
        logging.info("ICE state: %s", pc.iceConnectionState)

    tts = TTSAudioTrack()
    pc.addTrack(tts)

    video_task_holder = {"task": None}

    @pc.on("track")
    def on_track(track):
        logging.info("Inbound track: %s", track.kind)
        if track.kind == "video":
            task = asyncio.ensure_future(consume_video_loop(track, tts))
            video_task_holder["task"] = task

        @track.on("ended")
        async def _on_ended():
            logging.info("Track %s ended", track.kind)
            if video_task_holder["task"]:
                video_task_holder["task"].cancel()

    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type=offer_type))

    # Greeting so you immediately hear something (validates routing)
    tts.enqueue_text("Connection established. Sign recognition and speech are now live.")

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    await _wait_ice_complete(pc, timeout=2.0)

    # Keep strong refs
    SESSIONS[id(pc)] = {"pc": pc, "tts": tts, "video_task": video_task_holder["task"]}

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


@app.route("/speak", methods=["POST"])
def speak():
    """Manual test: POST {"text": "hello there"}"""
    data = request.get_json(force=True)
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "missing text"}), 400

    count = 0
    for sess in list(SESSIONS.values()):
        tts: TTSAudioTrack = sess.get("tts")
        if tts:
            tts.enqueue_text(text)
            count += 1
    return jsonify({"ok": True, "sessions": count}), 200


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
    # IMPORTANT: keep debug=False so the dev reloader doesn't kill our asyncio loop
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
