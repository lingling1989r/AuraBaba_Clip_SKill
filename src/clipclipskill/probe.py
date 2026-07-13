from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def run_ffprobe(video_path: Path) -> dict[str, Any]:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobe is not installed or not in PATH")
    if not video_path.exists():
        raise FileNotFoundError(f"video not found: {video_path}")

    command = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def normalize_probe(raw_probe: dict[str, Any], video_path: Path) -> dict[str, Any]:
    format_info = raw_probe.get("format", {})
    streams = raw_probe.get("streams", [])
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})

    duration_sec = float(format_info.get("duration") or 0.0)
    size_bytes = int(format_info.get("size") or video_path.stat().st_size)

    return {
        "file_name": video_path.name,
        "file_path": str(video_path),
        "duration_sec": duration_sec,
        "size_bytes": size_bytes,
        "bit_rate": int(format_info.get("bit_rate") or 0),
        "format_name": format_info.get("format_name"),
        "video": {
            "codec": video_stream.get("codec_name"),
            "width": int(video_stream.get("width") or 0),
            "height": int(video_stream.get("height") or 0),
            "fps": video_stream.get("r_frame_rate"),
        },
        "audio": {
            "present": bool(audio_stream),
            "codec": audio_stream.get("codec_name"),
            "channels": int(audio_stream.get("channels") or 0),
            "sample_rate": int(audio_stream.get("sample_rate") or 0),
        },
        "raw": raw_probe,
    }


def probe_video(video_path: Path) -> dict[str, Any]:
    raw = run_ffprobe(video_path)
    return normalize_probe(raw, video_path)
