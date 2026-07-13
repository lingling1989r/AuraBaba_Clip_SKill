from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUNTIME_ROOT = REPO_ROOT / "runtime"
DEFAULT_JOBS_ROOT = DEFAULT_RUNTIME_ROOT / "jobs"
WORKSPACE_ENV_VAR = "CLIPCLIPSKILL_WORKSPACE"
WORKSPACE_CONFIG_PATH = REPO_ROOT / ".clipclipskill-workspace.json"


@dataclass(frozen=True)
class JobWorkspace:
    job_id: str
    root: Path
    jobs_root: Path
    intake_path: Path
    status_path: Path
    source_dir: Path
    probe_dir: Path
    audio_dir: Path
    transcript_dir: Path
    diarization_dir: Path
    planning_dir: Path
    clips_dir: Path
    ops_dir: Path
    logs_dir: Path


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str, fallback: str = "item") -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or fallback


def sha256_file(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_job_id(video_path: Path | None = None, file_hash: str | None = None, *, source_label: str | None = None) -> str:
    if video_path is not None:
        source_hash = file_hash or sha256_file(video_path)
        return f"{slugify(video_path.stem, fallback='video')}__{source_hash[:8]}"
    if not source_label:
        raise ValueError("source_label is required when video_path is not provided")
    source_hash = hashlib.sha256(source_label.encode("utf-8")).hexdigest()
    return f"{slugify(source_label, fallback='video')}__{source_hash[:8]}"


def read_workspace_binding(config_path: Path = WORKSPACE_CONFIG_PATH) -> Path | None:
    if not config_path.exists():
        return None
    payload = read_json(config_path)
    workspace_dir = payload.get("workspace_dir")
    if not workspace_dir:
        return None
    return Path(str(workspace_dir)).expanduser().resolve()


def write_workspace_binding(workspace_dir: str | Path, config_path: Path = WORKSPACE_CONFIG_PATH) -> Path:
    resolved = Path(workspace_dir).expanduser().resolve()
    write_json(config_path, {"workspace_dir": str(resolved)})
    return resolved


def clear_workspace_binding(config_path: Path = WORKSPACE_CONFIG_PATH) -> None:
    if config_path.exists():
        config_path.unlink()


def resolve_jobs_root(base_dir: str | Path | None = None) -> Path:
    if base_dir is not None:
        root = Path(base_dir).expanduser().resolve()
    else:
        configured = os.environ.get(WORKSPACE_ENV_VAR)
        if configured:
            root = Path(configured).expanduser().resolve()
        else:
            bound = read_workspace_binding()
            root = bound if bound is not None else DEFAULT_JOBS_ROOT
    return root


def get_job_workspace(job_id: str, base_dir: str | Path | None = None) -> JobWorkspace:
    jobs_root = resolve_jobs_root(base_dir)
    root = jobs_root / job_id
    return JobWorkspace(
        job_id=job_id,
        root=root,
        jobs_root=jobs_root,
        intake_path=root / "intake.json",
        status_path=root / "status.json",
        source_dir=root / "source",
        probe_dir=root / "probe",
        audio_dir=root / "audio",
        transcript_dir=root / "transcript",
        diarization_dir=root / "diarization",
        planning_dir=root / "planning_package",
        clips_dir=root / "clips",
        ops_dir=root / "ops",
        logs_dir=root / "logs",
    )


def create_job_workspace(job_id: str, base_dir: str | Path | None = None) -> JobWorkspace:
    workspace = get_job_workspace(job_id, base_dir)
    ensure_dir(workspace.root)
    ensure_dir(workspace.source_dir)
    ensure_dir(workspace.probe_dir)
    ensure_dir(workspace.audio_dir)
    ensure_dir(workspace.transcript_dir)
    ensure_dir(workspace.diarization_dir)
    ensure_dir(workspace.planning_dir)
    ensure_dir(workspace.clips_dir)
    ensure_dir(workspace.ops_dir)
    ensure_dir(workspace.logs_dir)
    return workspace


def write_json(file_path: Path, data: Any) -> None:
    ensure_dir(file_path.parent)
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_json(file_path: Path) -> Any:
    with file_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_text(file_path: Path, content: str) -> None:
    ensure_dir(file_path.parent)
    file_path.write_text(content, encoding="utf-8")


def relative_to_job(job_root: Path, target: Path) -> str:
    return target.relative_to(job_root).as_posix()


def clip_output_stem(sequence: int, topic: str) -> str:
    return f"{slugify(topic, fallback='clip')}_{sequence:03d}"
