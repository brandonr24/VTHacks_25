"use client";

import { useEffect, useRef, useState } from "react";
import Combobox from "./ComboBox";

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || "";
const OFFER_URL = `${BACKEND}/webrtc/offer`;
const TTS_URL = (txt) => `${BACKEND}/tts?text=${encodeURIComponent(txt)}`;

export default function ASLVoiceClient() {
  const videoRef = useRef(null);
  const audioRef = useRef(null);           // sinks WebAudio destination stream
  const pcRef = useRef(null);
  const dcRef = useRef(null);
  const localStreamRef = useRef(null);

  const audioCtxRef = useRef(null);
  const destNodeRef = useRef(null);

  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState("Idle");
  const [outputs, setOutputs] = useState([]);
  const [chosenOutputId, setChosenOutputId] = useState("");
  const [flipV, setFlipV] = useState(true);

  function log(s) {
    setStatus(s);
    console.log(s);
  }

  // --- Set up WebAudio graph that we can route to a virtual output
  async function setupAudioGraph() {
    if (audioCtxRef.current) return;
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const dest = ac.createMediaStreamDestination();
    audioCtxRef.current = ac;
    destNodeRef.current = dest;

    // an <audio> element that plays the WebAudio stream
    const el = audioRef.current;
    el.autoplay = true;
    el.srcObject = dest.stream;

    // user gesture already happened when Start button was clicked
    try { await el.play(); } catch (_) {}
  }

  async function playBytesToVirtualMic(arrayBuffer) {
    const ac = audioCtxRef.current;
    const dest = destNodeRef.current;
    if (!ac || !dest) return;

    const buf = await ac.decodeAudioData(arrayBuffer.slice(0));
    const src = ac.createBufferSource();
    src.buffer = buf;
    src.connect(dest);
    src.start();
  }

  // --- Media capture (video only)
  async function getCamera() {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 360 }, frameRate: { ideal: 24, max: 30 } },
      audio: false,
    });
    localStreamRef.current = stream;
    if (videoRef.current) videoRef.current.srcObject = stream;
  }

  // --- Create peer connection, wire tracks/events, create DataChannel
  async function createPC() {
    const pc = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }],
    });

    pc.addEventListener("iceconnectionstatechange", () => {
      console.log("ICE:", pc.iceConnectionState);
      if (["connected", "completed"].includes(pc.iceConnectionState)) {
        setConnected(true);
        log("WebRTC connected.");
      }
      if (["failed", "disconnected"].includes(pc.iceConnectionState)) {
        setConnected(false);
        log(`ICE state: ${pc.iceConnectionState}`);
      }
    });

    // Upstream: send only the video track(s)
    const vTracks = (localStreamRef.current?.getVideoTracks()) || [];
    vTracks.forEach((t) => pc.addTrack(t, localStreamRef.current));

    // Data channel (frontend-initiated). Backend will attach to it and send text.
    const dc = pc.createDataChannel("tts-text");
    dc.onopen = () => log("DataChannel open (tts-text).");
    dc.onclose = () => log("DataChannel closed.");
    dc.onmessage = async (e) => {
      const text = String(e.data || "").trim();
      if (!text) return;
      // fetch audio bytes from backend and play via WebAudio -> chosen output
      try {
        const res = await fetch(TTS_URL(text));
        if (!res.ok) throw new Error(`TTS ${res.status}`);
        const buf = await res.arrayBuffer();
        await playBytesToVirtualMic(buf);
      } catch (err) {
        console.error("TTS fetch/play failed:", err);
      }
    };

    pcRef.current = pc;
    dcRef.current = dc;
  }

  // Wait for ICE gathering complete (helps when backend doesn't use trickle)
  function waitForIceGatheringComplete(pc, timeoutMs = 2000) {
    if (pc.iceGatheringState === "complete") return Promise.resolve();
    return new Promise((resolve) => {
      const timer = setTimeout(() => {
        pc.removeEventListener("icegatheringstatechange", onState);
        resolve();
      }, timeoutMs);
      function onState() {
        if (pc.iceGatheringState === "complete") {
          clearTimeout(timer);
          pc.removeEventListener("icegatheringstatechange", onState);
          resolve();
        }
      }
      pc.addEventListener("icegatheringstatechange", onState);
    });
  }

  // --- SDP offer/answer with backend
  async function negotiate() {
    const pc = pcRef.current;
    if (!pc) throw new Error("PeerConnection not created.");

    // We don't expect any remote audio track now (TTS is client-side).
    const offer = await pc.createOffer({ offerToReceiveAudio: false, offerToReceiveVideo: false });
    await pc.setLocalDescription(offer);

    await waitForIceGatheringComplete(pc);

    const res = await fetch(OFFER_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sdp: pc.localDescription.sdp, type: pc.localDescription.type }),
    });
    if (!res.ok) throw new Error(`Offer failed: ${res.status}`);
    const ans = await res.json();
    await pc.setRemoteDescription({ type: "answer", sdp: ans.sdp });

    log("Connected – streaming video; TTS will play locally via selected output.");
  }

  // --- Lifecycle controls
  async function start() {
    try {
      await setupAudioGraph();
      await getCamera();
      await createPC();
      await negotiate();
    } catch (e) {
      console.error(e);
      log(`Failed to start: ${e?.message || e}`);
    }
  }

  async function stop() {
    try {
      pcRef.current?.getSenders().forEach((s) => s.track?.stop());
      pcRef.current?.close();
    } catch (e) {}

    pcRef.current = null;
    dcRef.current = null;

    try {
      localStreamRef.current?.getTracks().forEach((t) => t.stop());
    } catch (e) {}
    localStreamRef.current = null;

    setConnected(false);
    log("Disconnected");
  }

  useEffect(() => {
    return () => { stop(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Output device selection (route audio to virtual mic)
  async function ensureDeviceLabels() {
    try { await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) {}
  }

  async function listOutputs() {
    await ensureDeviceLabels();
    const devices = await navigator.mediaDevices.enumerateDevices();
    const outs = devices.filter((d) => d.kind === "audiooutput");
    setOutputs(outs);
    const preferred = outs.find((d) => /cable|blackhole|loopback|virtual/i.test(d.label));
    if (preferred) setChosenOutputId(preferred.deviceId);
    log("Pick your virtual output and click \"Use This Output\".");
  }

  async function applyOutput() {
    const el = audioRef.current;
    if (!el) return;
    if (!("setSinkId" in el)) {
      log("setSinkId not supported, route at OS level.");
      return;
    }
    try {
      await el.setSinkId(chosenOutputId || "default");
      const match = outputs.find((o) => o.deviceId === chosenOutputId);
      log(`Audio routed to: ${match?.label || "default"}.`);
    } catch (e) {
      console.error(e);
      log("Failed to set output. You can still route at OS level.");
    }
  }

  return (
    <div className="flex-col">
      {/* Local preview & controls */}
      <div className="rounded-2xl border-[1px] border-zinc-800 bg-[#141414cc] p-6 w-full shadow-sm mb-6 text-black">
        <div className="relative">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="h-[500px] w-full rounded-xl bg-black object-cover"
            style={{ transform: flipV ? "scaleX(-1)" : "none" }}
          />
        </div>

        <div className="flex-between w-full mt-4">
          <div className="flex items-center gap-3">
            <button
              onClick={start}
              className="rounded-xl border-[2px] border-black bg-white py-2 px-5 text-black transition-all hover:bg-black hover:text-white text-center text-sm font-inter flex items-center justify-center"
              disabled={connected}
            >
              Start Streaming
            </button>
            <button
              onClick={stop}
              className="rounded-xl border-[2px] border-black bg-white py-2 px-5 text-black transition-all hover:bg-black hover:text-white text-center text-sm font-inter flex items-center justify-center"
            >
              Stop
            </button>
          </div>
          <div>
            <p className="text-right text-sm text-white">{status}</p>
          </div>
        </div>
      </div>

      {/* Output routing */}
      <div className="rounded-2xl border border-neutral-200 bg-white p-4 shadow-sm">
        <h2 className="text-lg font-medium">Route audio to virtual microphone</h2>
        <p className="mt-1 text-sm text-neutral-600">
          Pick your virtual output (VB-CABLE on Windows, BlackHole on macOS). Then select that device as the
          <em> microphone</em> in Zoom/Meet.
        </p>

        <div className="mt-4 flex-between">
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={listOutputs}
              className="rounded-xl border border-neutral-300 px-4 py-2 hover:bg-neutral-50 text-sm"
            >
              List Devices
            </button>
            <Combobox
              items={[{ value: "", label: "(choose an output)" }, ...outputs.map((d) => ({ value: d.deviceId, label: d.label || d.deviceId }))]}
              value={chosenOutputId}
              onChange={(v) => setChosenOutputId(v)}
              placeholder="(choose an output)"
              searchablePlaceholder="Search outputs..."
            />
          </div>
          <button
            onClick={applyOutput}
            className="rounded-xl bg-neutral-900 px-4 py-2 text-white hover:bg-neutral-800 text-sm"
          >
            Use This Output
          </button>
        </div>

        {/* Hidden audio element that plays WebAudio destination (so we can setSinkId) */}
        <audio ref={audioRef} className="hidden" />
      </div>
    </div>
  );
}
