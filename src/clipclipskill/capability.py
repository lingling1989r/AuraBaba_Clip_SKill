from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

from .diarize import decide_diarization


MIN_FREE_DISK_BYTES = 2 * 1024 * 1024 * 1024
MIN_TOTAL_MEMORY_BYTES = 4 * 1024 * 1024 * 1024
MIN_AVAILABLE_MEMORY_BYTES = int(1.5 * 1024 * 1024 * 1024)
CPU_SMALL_MODEL_VIDEO_SECONDS = 90 * 60


def _find_spec(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _safe_sysconf(name: str) -> int | None:
    try:
        return int(os.sysconf(name))
    except (AttributeError, OSError, ValueError):
        return None


def _memory_total_bytes() -> int | None:
    page_size = _safe_sysconf("SC_PAGE_SIZE")
    page_count = _safe_sysconf("SC_PHYS_PAGES")
    if page_size is None or page_count is None:
        return None
    return page_size * page_count


def _memory_available_bytes() -> int | None:
    page_size = _safe_sysconf("SC_PAGE_SIZE")
    page_count = _safe_sysconf("SC_AVPHYS_PAGES")
    if page_size is None or page_count is None:
        return None
    return page_size * page_count


def _has_hf_token() -> bool:
    return bool(os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN"))


def _torch_details() -> dict[str, Any]:
    if not _find_spec("torch"):
        return {"available": False, "cuda_available": False}

    try:
        import torch
    except Exception:
        return {"available": True, "cuda_available": False}

    try:
        cuda_available = bool(torch.cuda.is_available())
    except Exception:
        cuda_available = False
    return {"available": True, "cuda_available": cuda_available}


def detect_local_capabilities(*, video_path: Path | None = None, normalized_probe: dict[str, Any] | None = None) -> dict[str, Any]:
    disk_target = video_path if video_path is not None else Path.cwd()
    disk_usage = shutil.disk_usage(disk_target)
    return {
        "tools": {
            "ffmpeg": bool(shutil.which("ffmpeg")),
            "ffprobe": bool(shutil.which("ffprobe")),
        },
        "imports": {
            "faster_whisper": _find_spec("faster_whisper"),
            "pyannote_audio": _find_spec("pyannote.audio"),
            "torch": _find_spec("torch"),
            "yt_dlp": _find_spec("yt_dlp"),
        },
        "torch": _torch_details(),
        "system": {
            "cpu_count": os.cpu_count() or 1,
            "memory_total_bytes": _memory_total_bytes(),
            "memory_available_bytes": _memory_available_bytes(),
            "disk_free_bytes": disk_usage.free,
        },
        "auth": {
            "has_hf_token": _has_hf_token(),
        },
        "input": {
            "audio_present": True if normalized_probe is None else bool(normalized_probe.get("audio", {}).get("present")),
        },
    }


def select_execution_profile(
    *,
    template_id: str,
    diarization_mode: str,
    duration_sec: float,
    language_hint: str,
    capabilities: dict[str, Any],
) -> dict[str, Any]:
    decision = decide_diarization(template_id, diarization_mode)
    warnings: list[str] = []
    blocking_reasons: list[str] = []

    tools = capabilities.get("tools", {})
    imports = capabilities.get("imports", {})
    torch = capabilities.get("torch", {})
    system = capabilities.get("system", {})
    auth = capabilities.get("auth", {})
    input_details = capabilities.get("input", {})

    if not tools.get("ffmpeg"):
        blocking_reasons.append("ffmpeg is not installed")
    if not tools.get("ffprobe"):
        blocking_reasons.append("ffprobe is not installed")
    if not imports.get("faster_whisper"):
        blocking_reasons.append("faster-whisper is not installed")
    if not input_details.get("audio_present", True):
        blocking_reasons.append("input video does not contain an audio track")

    total_memory_bytes = system.get("memory_total_bytes")
    available_memory_bytes = system.get("memory_available_bytes")
    disk_free_bytes = system.get("disk_free_bytes")

    if isinstance(total_memory_bytes, int) and total_memory_bytes < MIN_TOTAL_MEMORY_BYTES:
        blocking_reasons.append("system memory is below the minimum 4 GB requirement")
    if isinstance(available_memory_bytes, int) and available_memory_bytes < MIN_AVAILABLE_MEMORY_BYTES:
        blocking_reasons.append("available memory is below the minimum 1.5 GB requirement")
    if isinstance(disk_free_bytes, int) and disk_free_bytes < MIN_FREE_DISK_BYTES:
        blocking_reasons.append("free disk space is below the minimum 2 GB requirement")

    device = "cuda" if torch.get("cuda_available") else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    asr_model = "medium"

    language_hint_normalized = language_hint.strip().lower() if language_hint else "auto"
    if device == "cuda" and language_hint_normalized in {"en", "english"}:
        asr_model = "distil-large-v3"
    elif device == "cpu":
        low_memory = isinstance(total_memory_bytes, int) and total_memory_bytes < 12 * 1024 * 1024 * 1024
        long_video = duration_sec >= CPU_SMALL_MODEL_VIDEO_SECONDS
        if low_memory or long_video:
            asr_model = "small"
            if low_memory:
                warnings.append("downgraded ASR model to small because the machine has limited memory")
            elif long_video:
                warnings.append("downgraded ASR model to small because the input video is long for CPU-only processing")

    diarization_enabled = bool(decision["enabled"])
    diarization_reason = decision["reason"]
    diarization_requirements_missing: list[str] = []
    if diarization_enabled and not imports.get("pyannote_audio"):
        diarization_requirements_missing.append("pyannote.audio is not installed")
    if diarization_enabled and not auth.get("has_hf_token"):
        diarization_requirements_missing.append("Hugging Face token is not configured")

    if diarization_requirements_missing:
        if diarization_mode == "on":
            blocking_reasons.extend(f"diarization requested but {reason}" for reason in diarization_requirements_missing)
        else:
            diarization_enabled = False
            diarization_reason = "auto-disabled because diarization requirements are unavailable"
            warnings.append("diarization disabled because local requirements are unavailable")

    if diarization_enabled and device == "cpu" and duration_sec >= 2 * 60 * 60:
        warnings.append("speaker diarization may be slow on CPU-only processing for videos over 2 hours")

    verdict = "blocked" if blocking_reasons else "degraded" if warnings else "ok"
    return {
        "verdict": verdict,
        "asr_backend": "faster-whisper",
        "asr_model": asr_model,
        "device": device,
        "compute_type": compute_type,
        "language_hint": language_hint,
        "diarization_enabled": diarization_enabled,
        "diarization_reason": diarization_reason,
        "warnings": warnings,
        "blocking_reasons": blocking_reasons,
        "resource_summary": {
            "cpu_count": system.get("cpu_count"),
            "memory_total_bytes": total_memory_bytes,
            "memory_available_bytes": available_memory_bytes,
            "disk_free_bytes": disk_free_bytes,
        },
    }
