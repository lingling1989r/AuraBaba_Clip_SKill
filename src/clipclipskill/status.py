from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .progress import build_initial_progress
from .workspace import read_json, write_json

PHASES = [
    "created",
    "probed",
    "awaiting_template_confirmation",
    "confirmed_for_transcription",
    "transcribing",
    "transcribed",
    "diarization_running",
    "analysis_ready",
    "awaiting_plan_confirmation",
    "approved_for_render",
    "rendering",
    "ops_generating",
    "validating",
    "completed",
    "failed",
]

ALLOWED_TRANSITIONS = {
    "created": {"probed", "failed"},
    "probed": {"awaiting_template_confirmation", "failed"},
    "awaiting_template_confirmation": {"confirmed_for_transcription", "failed"},
    "confirmed_for_transcription": {"transcribing", "failed"},
    "transcribing": {"transcribed", "failed"},
    "transcribed": {"diarization_running", "analysis_ready", "failed"},
    "diarization_running": {"analysis_ready", "failed"},
    "analysis_ready": {"awaiting_plan_confirmation", "failed"},
    "awaiting_plan_confirmation": {"approved_for_render", "failed"},
    "approved_for_render": {"rendering", "failed"},
    "rendering": {"ops_generating", "failed"},
    "ops_generating": {"validating", "failed"},
    "validating": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
}


class StatusError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build_initial_status(
    *,
    job_id: str,
    source_kind: str,
    input_video_path: str | None,
    source_sha256: str | None,
    origin_path: str | None,
    origin_url: str | None,
    platform: str | None,
    template_id: str,
    length_mode: str,
    target_seconds: int | None,
    transcription_mode: str,
    diarization_mode: str,
    language_hint: str,
) -> dict[str, Any]:
    return {
        "schema_version": "1.1",
        "job_id": job_id,
        "phase": "created",
        "source": {
            "kind": source_kind,
            "input_video_path": input_video_path,
            "source_sha256": source_sha256,
            "origin_path": origin_path,
            "origin_url": origin_url,
            "resolved_url": None,
            "platform": platform,
            "download_status": "skipped" if source_kind == "local" else "pending",
            "downloaded_video_path": None,
            "downloader": None,
            "duration_sec": None,
            "size_bytes": None,
        },
        "template": {
            "suggested": template_id,
            "confirmed": None,
            "confidence": 1.0,
        },
        "preferences": {
            "length_mode": length_mode,
            "target_seconds": target_seconds,
            "transcription_mode": transcription_mode,
            "diarization_mode": diarization_mode,
            "language_hint": language_hint,
        },
        "artifacts": {
            "probe": None,
            "capability": None,
            "execution_profile": None,
            "estimate": None,
            "progress_log": None,
            "download_metadata": None,
            "audio": None,
            "transcript_segments": None,
            "transcript_text": None,
            "transcript_srt": None,
            "transcript_vtt": None,
            "utterances": None,
            "diarization": None,
            "template_decision": None,
            "segment_candidates": None,
            "clip_plan": None,
            "publish_manifest": None,
            "operations_manual": None,
            "full_article_markdown": None,
            "full_article_docx": None,
            "full_article_pdf": None,
            "validation_report": None,
        },
        "confirmations": {
            "template_gate": {
                "required": True,
                "confirmed": False,
                "confirmed_at": None,
            },
            "plan_gate": {
                "required": True,
                "confirmed": False,
                "confirmed_at": None,
            },
        },
        "preflight": {
            "verdict": "pending",
            "checked_at": None,
            "warnings": [],
            "blocking_reasons": [],
        },
        "execution_profile": None,
        "progress": build_initial_progress(),
        "history": [
            {
                "phase": "created",
                "at": now_iso(),
                "note": "job created",
            }
        ],
        "errors": [],
    }


def load_status(status_path: Path) -> dict[str, Any]:
    return read_json(status_path)


def save_status(status_path: Path, status: dict[str, Any]) -> None:
    write_json(status_path, status)


def transition_status(status: dict[str, Any], new_phase: str, note: str | None = None) -> dict[str, Any]:
    current = status["phase"]
    if new_phase not in PHASES:
        raise StatusError(f"unknown phase: {new_phase}")
    if new_phase != current and new_phase not in ALLOWED_TRANSITIONS[current]:
        raise StatusError(f"illegal phase transition: {current} -> {new_phase}")

    updated = deepcopy(status)
    updated["phase"] = new_phase
    updated["history"].append(
        {
            "phase": new_phase,
            "at": now_iso(),
            "note": note or f"transitioned from {current}",
        }
    )
    return updated


def mark_artifact(status: dict[str, Any], key: str, relative_path: str) -> dict[str, Any]:
    updated = deepcopy(status)
    updated["artifacts"][key] = relative_path
    return updated


def update_source_metadata(status: dict[str, Any], *, duration_sec: float, size_bytes: int) -> dict[str, Any]:
    updated = deepcopy(status)
    updated["source"]["duration_sec"] = duration_sec
    updated["source"]["size_bytes"] = size_bytes
    return updated


def update_source_materialization(
    status: dict[str, Any],
    *,
    input_video_path: str,
    source_sha256: str,
    resolved_url: str | None,
    platform: str | None,
    downloaded_video_path: str | None,
    downloader: str | None,
    download_status: str,
) -> dict[str, Any]:
    updated = deepcopy(status)
    updated["source"]["input_video_path"] = input_video_path
    updated["source"]["source_sha256"] = source_sha256
    updated["source"]["resolved_url"] = resolved_url
    updated["source"]["platform"] = platform
    updated["source"]["downloaded_video_path"] = downloaded_video_path
    updated["source"]["downloader"] = downloader
    updated["source"]["download_status"] = download_status
    return updated


def confirm_template(
    status: dict[str, Any],
    *,
    template_id: str,
    length_mode: str,
    target_seconds: int | None,
    transcription_mode: str,
    diarization_mode: str,
) -> dict[str, Any]:
    updated = deepcopy(status)
    updated["template"]["confirmed"] = template_id
    updated["confirmations"]["template_gate"]["confirmed"] = True
    updated["confirmations"]["template_gate"]["confirmed_at"] = now_iso()
    updated["preferences"]["length_mode"] = length_mode
    updated["preferences"]["target_seconds"] = target_seconds
    updated["preferences"]["transcription_mode"] = transcription_mode
    updated["preferences"]["diarization_mode"] = diarization_mode
    return updated


def confirm_plan(status: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(status)
    updated["confirmations"]["plan_gate"]["confirmed"] = True
    updated["confirmations"]["plan_gate"]["confirmed_at"] = now_iso()
    return updated


def update_preflight(status: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(status)
    updated["preflight"] = {
        "verdict": profile["verdict"],
        "checked_at": now_iso(),
        "warnings": list(profile.get("warnings", [])),
        "blocking_reasons": list(profile.get("blocking_reasons", [])),
    }
    updated["execution_profile"] = deepcopy(profile)
    return updated


def update_progress(status: dict[str, Any], progress: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(status)
    updated["progress"] = deepcopy(progress)
    return updated


def record_error(status: dict[str, Any], message: str) -> dict[str, Any]:
    updated = deepcopy(status)
    updated["errors"].append({"at": now_iso(), "message": message})
    return updated


def require_phase(status: dict[str, Any], allowed_phases: set[str], action: str) -> None:
    if status["phase"] not in allowed_phases:
        raise StatusError(f"cannot {action} while phase is {status['phase']}")


def next_action(status: dict[str, Any]) -> str:
    phase = status["phase"]
    if phase == "created":
        return "probe"
    if phase in {"probed", "awaiting_template_confirmation"}:
        return "confirm_template"
    if phase == "confirmed_for_transcription":
        return "transcribe"
    if phase in {"transcribed", "analysis_ready"}:
        return "plan"
    if phase == "awaiting_plan_confirmation":
        return "approve_plan"
    if phase == "approved_for_render":
        return "render"
    if phase == "ops_generating":
        return "ops"
    if phase == "validating":
        return "validate"
    if phase == "completed":
        return "done"
    if phase == "failed":
        return "inspect_errors"
    return "continue"
