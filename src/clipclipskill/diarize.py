from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .templates import diarization_default
from .workspace import write_json


HF_TOKEN_ENV_KEYS = ("HF_TOKEN", "HUGGINGFACE_HUB_TOKEN")


def _hf_token() -> str | None:
    for key in HF_TOKEN_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            return value
    return None


def decide_diarization(template_id: str, diarization_mode: str) -> dict[str, Any]:
    default_enabled = diarization_default(template_id)
    if diarization_mode == "on":
        enabled = True
        reason = "user forced diarization"
    elif diarization_mode == "off":
        enabled = False
        reason = "user disabled diarization"
    else:
        enabled = default_enabled
        reason = "template default applied"

    return {
        "template_id": template_id,
        "diarization_mode": diarization_mode,
        "enabled": enabled,
        "reason": reason,
        "estimated_extra_minutes": 8 if enabled else 0,
    }


def write_template_decision(output_path: Path, decision: dict[str, Any]) -> Path:
    write_json(output_path, decision)
    return output_path


def run_stub_diarization(output_path: Path) -> Path:
    payload = {
        "engine": "stub-diarization",
        "speaker_count_estimate": 2,
        "overlap_ratio": 0.03,
        "confidence": 0.72,
        "segments": [
            {"start": 0.0, "end": 30.0, "speaker": "SPEAKER_00"},
            {"start": 30.0, "end": 90.0, "speaker": "SPEAKER_01"},
            {"start": 90.0, "end": 126.0, "speaker": "SPEAKER_00"}
        ]
    }
    write_json(output_path, payload)
    return output_path


def run_pyannote_diarization(audio_path: Path, output_path: Path) -> Path:
    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise RuntimeError("pyannote.audio is not installed") from exc

    token = _hf_token()
    if not token:
        raise RuntimeError("Hugging Face token is not configured")

    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
    diarization = pipeline(str(audio_path))

    segments = []
    speakers: set[str] = set()
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        speaker_name = str(speaker)
        speakers.add(speaker_name)
        segments.append(
            {
                "start": round(float(turn.start), 3),
                "end": round(float(turn.end), 3),
                "speaker": speaker_name,
            }
        )

    if not segments:
        raise RuntimeError("diarization produced no speaker segments")

    payload = {
        "engine": "pyannote.audio",
        "speaker_count_estimate": len(speakers),
        "overlap_ratio": 0.0,
        "confidence": None,
        "segments": segments,
    }
    write_json(output_path, payload)
    return output_path


def diarize_audio(audio_path: Path, output_path: Path, *, allow_stub_fallback: bool = False) -> Path:
    try:
        return run_pyannote_diarization(audio_path, output_path)
    except Exception:
        if not allow_stub_fallback:
            raise
        return run_stub_diarization(output_path)
