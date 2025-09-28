from __future__ import annotations
import os
import sys
import argparse
from pathlib import Path
import cv2
import json
from pathlib import Path
from typing import Any, Dict

extract_file = "extracted_images"
data_file = "MSASL_train.json"
fps_for_all = 1

def load_json(path: str | Path) -> Any:
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

# ---- Downloaders ----
def download_with_pytube(url: str, output_dir: Path) -> Path:
    from pytube import YouTube
    try:
        yt = None
        yt = YouTube(url)
        stream = yt.streams.get_highest_resolution()  # progressive .mp4 when available
        print(f"[pytube] Downloading: {yt.title}")
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = Path(stream.download(output_path=str(output_dir)))
        print(f"[pytube] Download complete: {file_path}")
        return file_path
    except Exception as e:
        raise RuntimeError(f"[pytube] Error downloading video: {e}")

def download_with_ytdlp(url: str, output_dir: Path) -> Path:
    """
    Uses yt-dlp. Requires ffmpeg for muxing best video+audio.
    """
    try:
        from yt_dlp import YoutubeDL
    except Exception:
        raise RuntimeError("yt-dlp not installed. Run: pip install yt-dlp")

    output_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(output_dir / "%(title).200s.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        "format": "bv*+ba/b",          # best video+audio or best single file
        "merge_output_format": "mp4",  # prefer mp4 (needs ffmpeg)
        "noprogress": True,
        "retries": 10,
        "fragment_retries": 10,
        "quiet": True,
        "http_headers": {"User-Agent": "Mozilla/5.0"},
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # prefer the path reported by yt-dlp
            if "requested_downloads" in info and info["requested_downloads"]:
                return Path(info["requested_downloads"][0]["filepath"])
            # fallback path resolution
            filename = ydl.prepare_filename(info)
            # If merged, ensure .mp4
            if not filename.lower().endswith(".mp4"):
                filename = os.path.splitext(filename)[0] + ".mp4"
            return Path(filename)
    except Exception as e:
        raise RuntimeError(f"[yt-dlp] Error downloading video: {e}")

# ---- Frame extraction ----
def extract_frames(video_path: Path, output_dir: Path, fps: float, image_file_name: str, start_frame: float, end_frame:float, frame_rates: int, size=(640, 640)):
    """
    Extract frames at a true N frames-per-second rate (fps>0).
    """
    if fps <= 0:
        raise ValueError("--fps must be > 0")
    
    output_loc = Path(extract_file)
    output_loc.mkdir(parents=True, exist_ok=True)

    output_dir = output_loc / image_file_name
    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Error: Could not open video file: {video_path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS)
    if not src_fps or src_fps <= 0:
        # fallback if container doesn't report FPS
        src_fps = 30.0

    # stride in frames (approx) to hit desired fps
    stride = max(int(round(src_fps / fps)), 1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
    saved = 0
    frame_idx = 0

    print(f"[extract] Source FPS ~ {src_fps:.3f}, target FPS {fps:.3f}, stride {stride}, total frames {total_frames}")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % stride == 0:
            interp = cv2.INTER_AREA if frame.shape[0] >= size[1] or frame.shape[1] >= size[0] else cv2.INTER_LINEAR
            resized = cv2.resize(frame, size, interpolation=interp)
            if frame_idx >= start_frame*frame_rates and frame_idx <= end_frame*frame_rates:
                cv2.imwrite(str(output_dir / f"frame_{frame_idx:06d}.jpg"), resized)
                saved += 1

        frame_idx += 1

    cap.release()
    print(f"[extract] Saved {saved} frames to: {output_dir}")

def safe_download(url: str, out_dir: Path) -> Path:
    """Try pytube first; on HTTP 400 or any failure, fall back to yt-dlp."""
    try:
        return download_with_pytube(url, out_dir)  # your existing function
    except Exception as e:
        # Many pytube failures manifest as HTTP Error 400; fallback is more reliable.
        print(f"[warn] pytube failed ({e}); trying yt-dlp…")
        return download_with_ytdlp(url, out_dir)

def main():
    config = load_json(data_file)
    for index, imageData in enumerate(config):
        skip = False
        url = (imageData['url'] or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            print("Usage: SaveData.py <YouTube URL>\nError: missing or invalid URL.")
        
        if not skip:

            out_dir = Path("Delete")
            frames_dir = Path(extract_file)

            skip = False

            try:
                video_path = safe_download(url, out_dir)
            except Exception as e:
                print(e)
                skip = True

            if not skip:
                try:
                    extract_frames(video_path, frames_dir, fps=fps_for_all, image_file_name=imageData['clean_text'], start_frame=imageData['start_time'], end_frame=imageData['end_time'], frame_rates=imageData['fps'])
                except Exception as e:
                    print(e)
                print("\nSuccessfully saved image", index)
                print(imageData['start_time'], imageData['end_time'], "\n")

if __name__ == "__main__":
    main()
