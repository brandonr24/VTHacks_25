import asyncio
import logging
import threading
from fractions import Fraction

import numpy as np
import av
from flask import Flask, request, jsonify
from flask_cors import CORS
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack

# ----- Flask setup -----
logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
# Allow Next.js dev server
CORS(app, resources={r"/*": {"origins": ["http://localhost:3000", "http://127.0.0.1:3000"]}})

# Run an asyncio loop in a background thread (Flask is sync)
loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()

pcs = set()


# ----- Synthetic audio (sine) -----
class SineAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, sample_rate=48000, freq=440.0, amplitude=0.15):
        super().__init__()
        self.sample_rate = int(sample_rate)
        self.freq = float(freq)
        self.amp = float(amplitude)
        self.samples_per_frame = 960  # 20 ms at 48 kHz (common Opus ptime)
        self._t0 = 0  # running sample index

    async def recv(self):
        # Pace: ~20 ms per audio packet
        await asyncio.sleep(self.samples_per_frame / self.sample_rate)

        # Generate mono sine wave
        n = self.samples_per_frame
        t = (np.arange(n, dtype=np.float32) + self._t0) / self.sample_rate
        tone = self.amp * np.sin(2 * np.pi * self.freq * t)

        # Convert to 16-bit signed integers
        samples_i16 = (tone * 32767.0).astype(np.int16)

        # IMPORTANT: PyAV expects (channels, samples) for AudioFrame.from_ndarray
        # For mono: shape = (1, n)
        samples_2d = samples_i16.reshape(1, -1)

        frame = av.AudioFrame.from_ndarray(samples_2d, format="s16", layout="mono")
        frame.sample_rate = self.sample_rate
        frame.pts = self._t0
        frame.time_base = Fraction(1, self.sample_rate)

        self._t0 += n
        return frame


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
    pcs.add(pc)

    @pc.on("iceconnectionstatechange")
    def _():
        logging.info("ICE state: %s", pc.iceConnectionState)
        if pc.iceConnectionState in ("failed", "closed", "disconnected"):
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        logging.info("Inbound track: %s", track.kind)
        # Just receiving the video is enough; no forwarding needed.
        @track.on("ended")
        async def _on_ended():
            logging.info("Track %s ended", track.kind)

    # Set remote description from browser
    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type=offer_type))

    # Add outbound audio (what browser will play / route to virtual mic)
    pc.addTrack(SineAudioTrack(freq=440.0))  # A4 tone

    # Create answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Give ICE a moment to gather candidates for non-trickle backends
    await _wait_ice_complete(pc, timeout=2.0)

    logging.info("Answer created")
    return pc.localDescription.sdp


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
        answer_sdp = fut.result(timeout=10)
    except Exception as e:
        logging.exception("Failed to create answer")
        return jsonify({"error": str(e)}), 500

    return jsonify({"sdp": answer_sdp, "type": "answer"}), 200


@app.route("/shutdown-peers", methods=["POST"])
def shutdown_peers():
    async def _close_all():
        tasks = []
        for pc in list(pcs):
            pcs.discard(pc)
            tasks.append(pc.close())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run_coroutine_threadsafe(_close_all(), loop).result(timeout=5)
    return jsonify({"ok": True, "remaining": len(pcs)}), 200


if __name__ == "__main__":
    # http://localhost:5001
    app.run(host="0.0.0.0", port=5001, debug=True, threaded=True)
