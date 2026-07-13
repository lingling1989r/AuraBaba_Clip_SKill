from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .workspace import ensure_dir, write_json, write_text


SAMPLE_RENDER_TEXT = "Rendered clip placeholder. Replace with ffmpeg output when media tooling is available.\n"
DEFAULT_AUDIO_SAMPLE_RATE = "48000"
DEFAULT_AUDIO_CHANNELS = "2"


def render_clip(
    source_video: Path,
    clips_dir: Path,
    artifact_dir: Path,
    *,
    sequence: int,
    title: str,
    stem: str,
    start_sec: float,
    end_sec: float,
) -> dict[str, str]:
    ensure_dir(clips_dir)
    ensure_dir(artifact_dir)
    clip_path = clips_dir / f"{stem}.mp4"
    srt_path = artifact_dir / f"{stem}.srt"
    manifest_path = artifact_dir / f"{stem}.json"

    if shutil.which("ffmpeg") and source_video.exists():
        command = _build_ffmpeg_render_command(source_video, clip_path, start_sec=start_sec, end_sec=end_sec)
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError:
            write_text(clip_path, SAMPLE_RENDER_TEXT)
    else:
        write_text(clip_path, SAMPLE_RENDER_TEXT)

    write_text(srt_path, f"1\n00:00:00,000 --> 00:00:05,000\n{title}\n")
    manifest = {
        "sequence": sequence,
        "title": title,
        "start_sec": start_sec,
        "end_sec": end_sec,
        "duration_sec": round(end_sec - start_sec, 2),
        "clip_path": str(clip_path),
        "subtitle_path": str(srt_path),
    }
    write_json(manifest_path, manifest)
    return {
        "clip": str(clip_path),
        "subtitle": str(srt_path),
        "manifest": str(manifest_path),
    }


def _build_ffmpeg_render_command(source_video: Path, clip_path: Path, *, start_sec: float, end_sec: float) -> list[str]:
    duration_sec = max(end_sec - start_sec, 0.1)
    return [
        "ffmpeg",
        "-y",
        "-ss",
        str(start_sec),
        "-i",
        str(source_video),
        "-t",
        f"{duration_sec:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-fflags",
        "+genpts",
        "-avoid_negative_ts",
        "make_zero",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-ar",
        DEFAULT_AUDIO_SAMPLE_RATE,
        "-ac",
        DEFAULT_AUDIO_CHANNELS,
        str(clip_path),
    ]
