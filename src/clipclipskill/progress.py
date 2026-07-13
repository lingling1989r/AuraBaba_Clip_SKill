from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

STEP_LABELS = {
    "probe": "Machine check",
    "transcribe": "Transcription",
    "plan": "Clip planning",
    "render": "Clip rendering",
    "ops": "Publish package generation",
    "validate": "Output validation",
}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build_initial_progress() -> dict[str, Any]:
    return {
        "started_at": None,
        "updated_at": now_iso(),
        "overall_percent": 0,
        "eta_seconds_remaining": None,
        "current_step": {
            "id": None,
            "label": None,
            "state": "pending",
            "eta_seconds": None,
            "message": "Job created",
        },
        "steps": [
            {"id": "probe", "label": STEP_LABELS["probe"], "state": "pending"},
            {"id": "transcribe", "label": STEP_LABELS["transcribe"], "state": "pending"},
            {"id": "plan", "label": STEP_LABELS["plan"], "state": "pending"},
            {"id": "render", "label": STEP_LABELS["render"], "state": "pending"},
            {"id": "ops", "label": STEP_LABELS["ops"], "state": "pending"},
            {"id": "validate", "label": STEP_LABELS["validate"], "state": "pending"},
        ],
    }


def humanize_eta_seconds(seconds: int | float | None) -> str:
    if seconds is None:
        return "unknown time"
    total = max(int(round(seconds)), 1)
    if total < 60:
        return f"~{total}s"
    minutes, remainder = divmod(total, 60)
    if minutes < 60:
        if remainder:
            return f"~{minutes}m {remainder}s"
        return f"~{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if minutes:
        return f"~{hours}h {minutes}m"
    return f"~{hours}h"


def format_started_message(label: str, eta_seconds: int | float | None, detail: str | None = None) -> str:
    message = f"Started {label.lower()} ({humanize_eta_seconds(eta_seconds)})"
    if detail:
        return f"{message}: {detail}"
    return message


def start_step(
    progress: dict[str, Any],
    *,
    step_id: str,
    label: str,
    eta_seconds: int | None,
    message: str,
    overall_percent: int,
    eta_seconds_remaining: int | None,
) -> dict[str, Any]:
    updated = deepcopy(progress)
    timestamp = now_iso()
    if updated["started_at"] is None:
        updated["started_at"] = timestamp
    updated["updated_at"] = timestamp
    updated["overall_percent"] = overall_percent
    updated["eta_seconds_remaining"] = eta_seconds_remaining
    updated["current_step"] = {
        "id": step_id,
        "label": label,
        "state": "in_progress",
        "eta_seconds": eta_seconds,
        "message": message,
    }
    for step in updated["steps"]:
        if step["id"] == step_id:
            step["state"] = "in_progress"
    return updated


def finish_step(
    progress: dict[str, Any],
    *,
    step_id: str,
    overall_percent: int,
    eta_seconds_remaining: int | None,
    message: str,
) -> dict[str, Any]:
    updated = deepcopy(progress)
    updated["updated_at"] = now_iso()
    updated["overall_percent"] = overall_percent
    updated["eta_seconds_remaining"] = eta_seconds_remaining
    if updated["current_step"]["id"] == step_id:
        updated["current_step"] = {
            "id": step_id,
            "label": STEP_LABELS.get(step_id, step_id),
            "state": "completed",
            "eta_seconds": 0,
            "message": message,
        }
    for step in updated["steps"]:
        if step["id"] == step_id:
            step["state"] = "completed"
    return updated
