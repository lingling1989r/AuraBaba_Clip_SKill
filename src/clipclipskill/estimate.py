from __future__ import annotations

from typing import Any


def estimate_processing_time(
    duration_sec: float,
    *,
    diarization_enabled: bool,
    clip_count_hint: int = 5,
    device: str = "cpu",
    asr_model: str = "medium",
) -> dict[str, Any]:
    duration_min = max(duration_sec / 60.0, 0.1)
    audio_extract_minutes = max(round(duration_min * 0.03, 2), 0.1)

    transcription_factor = 0.55
    if device == "cuda":
        transcription_factor = 0.18 if asr_model == "distil-large-v3" else 0.22
    elif asr_model == "small":
        transcription_factor = 0.35

    transcription_minutes = max(round(duration_min * transcription_factor, 2), 0.3)
    diarization_minutes = round(duration_min * (0.75 if device == "cpu" else 0.35), 2) if diarization_enabled else 0.0
    planning_minutes = max(round(clip_count_hint * 0.2, 2), 0.2)
    render_minutes = max(round(clip_count_hint * 0.5, 2), 0.5)
    ops_minutes = 0.2
    validate_minutes = max(round(clip_count_hint * 0.08, 2), 0.1)
    probe_minutes = 0.17

    step_minutes = {
        "probe": probe_minutes,
        "transcribe": round(audio_extract_minutes + transcription_minutes, 2),
        "plan": round(planning_minutes + diarization_minutes, 2),
        "render": render_minutes,
        "ops": ops_minutes,
        "validate": validate_minutes,
    }
    step_eta_seconds = {key: max(int(round(value * 60)), 1) for key, value in step_minutes.items()}
    total = round(sum(step_minutes.values()), 2)
    return {
        "audio_extract_minutes": audio_extract_minutes,
        "transcription_minutes": transcription_minutes,
        "diarization_minutes": diarization_minutes,
        "planning_minutes": planning_minutes,
        "render_minutes": render_minutes,
        "ops_minutes": ops_minutes,
        "validate_minutes": validate_minutes,
        "probe_minutes": probe_minutes,
        "step_minutes": step_minutes,
        "step_eta_seconds": step_eta_seconds,
        "total_estimated_minutes": total,
        "assumptions": [
            "Whisper-first local transcription",
            f"execution_device={device}",
            f"asr_model={asr_model}",
            "topic-complete clip planning",
            f"clip_count_hint={clip_count_hint}",
        ],
    }
