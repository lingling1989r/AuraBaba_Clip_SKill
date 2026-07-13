from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .analysis import build_utterances, write_utterances
from .audio import extract_audio
from .capability import detect_local_capabilities, select_execution_profile
from .diarize import decide_diarization, diarize_audio, write_template_decision
from .downloader import download_video_source, validate_supported_url
from .estimate import estimate_processing_time
from .ops_copy import (
    build_full_article,
    build_publish_copy,
    write_full_article_assets,
    write_operations_manual,
    write_publish_copy,
    write_publish_manifest,
)
from .plan import build_clip_plan, write_plan_outputs
from .probe import probe_video
from .progress import STEP_LABELS, finish_step, format_started_message, start_step
from .render import render_clip
from .score import score_candidates
from .segment import build_segment_candidates
from .status import (
    StatusError,
    build_initial_status,
    confirm_plan,
    confirm_template,
    load_status,
    mark_artifact,
    next_action,
    record_error,
    require_phase,
    save_status,
    transition_status,
    update_preflight,
    update_progress,
    update_source_materialization,
    update_source_metadata,
)
from .templates import resolve_template, validate_template_id
from .transcribe import transcribe_audio
from .validation import validate_clips, validate_publish_outputs, write_validation_report
from .workspace import (
    WORKSPACE_ENV_VAR,
    clear_workspace_binding,
    create_job_workspace,
    get_job_workspace,
    make_job_id,
    read_json,
    read_workspace_binding,
    relative_to_job,
    resolve_jobs_root,
    sha256_file,
    write_json,
    write_workspace_binding,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="clipclipskill")
    parser.add_argument(
        "--workspace-dir",
        help="directory where job folders and generated outputs are created",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor")
    doctor.set_defaults(func=cmd_doctor)

    bind_workspace = subparsers.add_parser("bind-workspace")
    bind_workspace.add_argument("directory")
    bind_workspace.set_defaults(func=cmd_bind_workspace)

    unbind_workspace = subparsers.add_parser("unbind-workspace")
    unbind_workspace.set_defaults(func=cmd_unbind_workspace)

    start_job = subparsers.add_parser("start-job")
    start_job_source = start_job.add_mutually_exclusive_group(required=True)
    start_job_source.add_argument("--video")
    start_job_source.add_argument("--url")
    start_job.add_argument("--template", required=True)
    start_job.add_argument("--length-mode", default="topic_complete")
    start_job.add_argument("--target-seconds", type=int)
    start_job.add_argument("--transcription-mode", default="whisper")
    start_job.add_argument("--diarization-mode", default="auto")
    start_job.add_argument("--language-hint", default="auto")
    start_job.set_defaults(func=cmd_start_job)

    probe = subparsers.add_parser("probe")
    probe.add_argument("--job-id", required=True)
    probe.set_defaults(func=cmd_probe)

    confirm = subparsers.add_parser("confirm-template")
    confirm.add_argument("--job-id", required=True)
    confirm.add_argument("--template", required=True)
    confirm.add_argument("--length-mode", default="topic_complete")
    confirm.add_argument("--target-seconds", type=int)
    confirm.add_argument("--transcription-mode", default="whisper")
    confirm.add_argument("--diarization-mode", default="auto")
    confirm.set_defaults(func=cmd_confirm_template)

    transcribe = subparsers.add_parser("transcribe")
    transcribe.add_argument("--job-id", required=True)
    transcribe.set_defaults(func=cmd_transcribe)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--job-id", required=True)
    plan.add_argument("--max-clips", type=int, default=3)
    plan.set_defaults(func=cmd_plan)

    approve = subparsers.add_parser("approve-plan")
    approve.add_argument("--job-id", required=True)
    approve.set_defaults(func=cmd_approve_plan)

    render = subparsers.add_parser("render")
    render.add_argument("--job-id", required=True)
    render.set_defaults(func=cmd_render)

    ops = subparsers.add_parser("ops")
    ops.add_argument("--job-id", required=True)
    ops.add_argument("--host-name")
    ops.add_argument("--guest-name")
    ops.add_argument("--article-title")
    ops.set_defaults(func=cmd_ops)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--job-id", required=True)
    validate.set_defaults(func=cmd_validate)

    resume = subparsers.add_parser("resume")
    resume.add_argument("--job-id", required=True)
    resume.set_defaults(func=cmd_resume)

    return parser.parse_args(argv)


def _resolve_workspace_dir(args: argparse.Namespace) -> Path | None:
    workspace_dir = getattr(args, "workspace_dir", None)
    return Path(workspace_dir).expanduser().resolve() if workspace_dir else None


def _load_workspace_status(job_id: str, args: argparse.Namespace | None = None) -> tuple[Any, dict[str, Any]]:
    workspace = get_job_workspace(job_id, _resolve_workspace_dir(args) if args is not None else None)
    status = load_status(workspace.status_path)
    return workspace, status


def _step_eta_seconds(estimate: dict[str, Any] | None, step_id: str) -> int | None:
    if not estimate:
        return None
    step_eta_seconds = estimate.get("step_eta_seconds", {})
    value = step_eta_seconds.get(step_id)
    return int(value) if value is not None else None


def _remaining_eta_seconds(estimate: dict[str, Any] | None, step_ids: list[str]) -> int | None:
    if not estimate:
        return None
    step_eta_seconds = estimate.get("step_eta_seconds", {})
    total = 0
    found = False
    for step_id in step_ids:
        value = step_eta_seconds.get(step_id)
        if value is not None:
            total += int(value)
            found = True
    return total if found else None


def _write_progress_artifact(workspace: Any, progress: dict[str, Any]) -> str:
    progress_path = workspace.logs_dir / "progress.json"
    write_json(progress_path, progress)
    return relative_to_job(workspace.root, progress_path)


def _start_progress_step(
    workspace: Any,
    status: dict[str, Any],
    *,
    step_id: str,
    estimate: dict[str, Any] | None,
    overall_percent: int,
    remaining_steps: list[str],
    detail: str | None = None,
) -> dict[str, Any]:
    eta_seconds = _step_eta_seconds(estimate, step_id)
    progress = start_step(
        status["progress"],
        step_id=step_id,
        label=STEP_LABELS[step_id],
        eta_seconds=eta_seconds,
        message=format_started_message(STEP_LABELS[step_id], eta_seconds, detail),
        overall_percent=overall_percent,
        eta_seconds_remaining=_remaining_eta_seconds(estimate, remaining_steps),
    )
    status = update_progress(status, progress)
    status = mark_artifact(status, "progress_log", _write_progress_artifact(workspace, progress))
    save_status(workspace.status_path, status)
    print(progress["current_step"]["message"])
    return status


def _finish_progress_step(
    workspace: Any,
    status: dict[str, Any],
    *,
    step_id: str,
    overall_percent: int,
    remaining_steps: list[str],
    message: str,
    estimate: dict[str, Any] | None,
) -> dict[str, Any]:
    progress = finish_step(
        status["progress"],
        step_id=step_id,
        overall_percent=overall_percent,
        eta_seconds_remaining=_remaining_eta_seconds(estimate, remaining_steps),
        message=message,
    )
    status = update_progress(status, progress)
    status = mark_artifact(status, "progress_log", _write_progress_artifact(workspace, progress))
    return status


def _required_dependencies(command: str, args: argparse.Namespace) -> list[str]:
    dependencies = ["ffmpeg", "ffprobe", "faster_whisper"]
    if command == "probe" and getattr(args, "job_id", None):
        try:
            _, status = _load_workspace_status(args.job_id, args)
        except Exception:
            return dependencies
        if status["source"]["kind"] == "url":
            dependencies.append("yt_dlp")
    if command == "start-job" and getattr(args, "url", None):
        dependencies.append("yt_dlp")
    diarization_mode = getattr(args, "diarization_mode", None)
    if diarization_mode == "on":
        dependencies.extend(["pyannote_audio", "hf_token"])
    return dependencies


DEPENDENCY_MESSAGES = {
    "ffmpeg": "ffmpeg is not installed",
    "ffprobe": "ffprobe is not installed",
    "faster_whisper": "faster-whisper is not installed",
    "pyannote_audio": "pyannote.audio is not installed",
    "yt_dlp": "yt-dlp is not installed",
    "hf_token": "Hugging Face token is not configured",
}


DEPENDENCY_IMPORT_KEYS = {
    "faster_whisper": "faster_whisper",
    "pyannote_audio": "pyannote_audio",
    "yt_dlp": "yt_dlp",
}


def _check_required_dependencies(command: str, args: argparse.Namespace) -> None:
    required = _required_dependencies(command, args)
    if not required:
        return
    capabilities = detect_local_capabilities()
    missing: list[str] = []
    for dependency in required:
        if dependency in {"ffmpeg", "ffprobe"}:
            if not capabilities["tools"].get(dependency):
                missing.append(DEPENDENCY_MESSAGES[dependency])
            continue
        if dependency == "hf_token":
            if not capabilities["auth"].get("has_hf_token"):
                missing.append(DEPENDENCY_MESSAGES[dependency])
            continue
        import_key = DEPENDENCY_IMPORT_KEYS[dependency]
        if not capabilities["imports"].get(import_key):
            missing.append(DEPENDENCY_MESSAGES[dependency])
    if missing:
        raise StatusError("missing required dependencies: " + "; ".join(missing))


def cmd_doctor(args: argparse.Namespace) -> int:
    capabilities = detect_local_capabilities()
    jobs_root = resolve_jobs_root(_resolve_workspace_dir(args))
    bound_workspace = read_workspace_binding()
    report = {
        "ffmpeg": capabilities["tools"]["ffmpeg"],
        "ffprobe": capabilities["tools"]["ffprobe"],
        "faster_whisper_import": capabilities["imports"]["faster_whisper"],
        "pyannote_audio_import": capabilities["imports"]["pyannote_audio"],
        "torch_import": capabilities["imports"]["torch"],
        "yt_dlp_import": capabilities["imports"]["yt_dlp"],
        "cuda_available": capabilities["torch"]["cuda_available"],
        "has_hf_token": capabilities["auth"]["has_hf_token"],
        "cpu_count": capabilities["system"]["cpu_count"],
        "memory_total_bytes": capabilities["system"]["memory_total_bytes"],
        "memory_available_bytes": capabilities["system"]["memory_available_bytes"],
        "disk_free_bytes": capabilities["system"]["disk_free_bytes"],
        "jobs_root": str(jobs_root),
        "workspace_env_var": WORKSPACE_ENV_VAR,
        "bound_workspace_dir": str(bound_workspace) if bound_workspace else None,
    }
    print_json(report)
    return 0


def cmd_bind_workspace(args: argparse.Namespace) -> int:
    resolved = write_workspace_binding(args.directory)
    print_json({"workspace_dir": str(resolved), "mode": "bound"})
    return 0


def cmd_unbind_workspace(_: argparse.Namespace) -> int:
    clear_workspace_binding()
    print_json({"mode": "unbound"})
    return 0


def cmd_start_job(args: argparse.Namespace) -> int:
    template_id = validate_template_id(resolve_template(args.template))

    if args.video:
        video_path = Path(args.video).expanduser().resolve()
        if not video_path.exists():
            raise FileNotFoundError(f"video not found: {video_path}")
        source_kind = "local"
        origin_path = str(video_path)
        origin_url = None
        platform = None
        source_hash = sha256_file(video_path)
        job_id = make_job_id(video_path, source_hash)
        intake_input = {"kind": source_kind, "video_path": str(video_path), "url": None}
        input_video_path = str(video_path)
    else:
        normalized_url, platform = validate_supported_url(args.url)
        source_kind = "url"
        origin_path = None
        origin_url = normalized_url
        source_hash = None
        job_id = make_job_id(source_label=normalized_url)
        intake_input = {"kind": source_kind, "video_path": None, "url": normalized_url}
        input_video_path = None

    workspace = create_job_workspace(job_id, _resolve_workspace_dir(args))

    intake = {
        "schema_version": "1.1",
        "job_id": job_id,
        "input": intake_input,
        "content_template_requested": template_id,
        "content_template_confirmed": False,
        "length_preference": {
            "mode": args.length_mode,
            "target_seconds": args.target_seconds,
        },
        "transcription": {
            "mode": args.transcription_mode,
            "confirmed": False,
        },
        "diarization": {
            "mode": args.diarization_mode,
            "confirmed": False,
        },
        "language_hint": args.language_hint,
    }
    status = build_initial_status(
        job_id=job_id,
        source_kind=source_kind,
        input_video_path=input_video_path,
        source_sha256=source_hash,
        origin_path=origin_path,
        origin_url=origin_url,
        platform=platform,
        template_id=template_id,
        length_mode=args.length_mode,
        target_seconds=args.target_seconds,
        transcription_mode=args.transcription_mode,
        diarization_mode=args.diarization_mode,
        language_hint=args.language_hint,
    )

    write_json(workspace.intake_path, intake)
    save_status(workspace.status_path, status)
    print_json({"job_id": job_id, "status_path": str(workspace.status_path)})
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    require_phase(status, {"created"}, "probe video")

    status = _start_progress_step(
        workspace,
        status,
        step_id="probe",
        estimate=None,
        overall_percent=5,
        remaining_steps=["probe"],
        detail="checking video metadata and machine readiness",
    )

    source = status["source"]
    if source["kind"] == "url" and not detect_local_capabilities()["imports"].get("yt_dlp"):
        raise StatusError("yt-dlp is not installed")

    if source["kind"] == "url":
        downloaded_video_path = source.get("downloaded_video_path")
        if downloaded_video_path and Path(downloaded_video_path).exists():
            video_path = Path(downloaded_video_path)
            status = update_source_materialization(
                status,
                input_video_path=str(video_path),
                source_sha256=source.get("source_sha256") or sha256_file(video_path),
                resolved_url=source.get("resolved_url") or source.get("origin_url"),
                platform=source.get("platform"),
                downloaded_video_path=str(video_path),
                downloader=source.get("downloader") or "yt-dlp",
                download_status="completed",
            )
            save_status(workspace.status_path, status)
        else:
            try:
                download_result = download_video_source(source["origin_url"], workspace.source_dir)
            except Exception as exc:
                status = record_error(status, f"download failed: {exc}")
                status = transition_status(status, "failed", "download failed")
                save_status(workspace.status_path, status)
                raise StatusError(str(exc)) from exc
            video_path = Path(str(download_result["local_video_path"]))
            status = update_source_materialization(
                status,
                input_video_path=str(video_path),
                source_sha256=str(download_result["source_sha256"]),
                resolved_url=str(download_result["resolved_url"]),
                platform=str(download_result["platform"]),
                downloaded_video_path=str(video_path),
                downloader=str(download_result["downloader"]),
                download_status="completed",
            )
            status = mark_artifact(
                status,
                "download_metadata",
                relative_to_job(workspace.root, Path(str(download_result["download_metadata_path"]))),
            )
            save_status(workspace.status_path, status)
    else:
        video_path = Path(status["source"]["input_video_path"])

    normalized = probe_video(video_path)
    capabilities = detect_local_capabilities(video_path=video_path, normalized_probe=normalized)
    template_id = status["template"]["confirmed"] or status["template"]["suggested"]
    profile = select_execution_profile(
        template_id=template_id,
        diarization_mode=status["preferences"]["diarization_mode"],
        duration_sec=normalized["duration_sec"],
        language_hint=status["preferences"]["language_hint"],
        capabilities=capabilities,
    )
    estimate = estimate_processing_time(
        normalized["duration_sec"],
        diarization_enabled=profile["diarization_enabled"],
        device=profile["device"],
        asr_model=profile["asr_model"],
    )

    probe_path = workspace.probe_dir / "probe.json"
    capability_path = workspace.probe_dir / "capability.json"
    profile_path = workspace.probe_dir / "execution_profile.json"
    estimate_path = workspace.probe_dir / "estimate.json"
    write_json(probe_path, normalized)
    write_json(capability_path, capabilities)
    write_json(profile_path, profile)
    write_json(estimate_path, estimate)

    status = update_source_metadata(
        status,
        duration_sec=normalized["duration_sec"],
        size_bytes=normalized["size_bytes"],
    )
    status = update_preflight(status, profile)
    status = mark_artifact(status, "probe", relative_to_job(workspace.root, probe_path))
    status = mark_artifact(status, "capability", relative_to_job(workspace.root, capability_path))
    status = mark_artifact(status, "execution_profile", relative_to_job(workspace.root, profile_path))
    status = mark_artifact(status, "estimate", relative_to_job(workspace.root, estimate_path))
    status = _finish_progress_step(
        workspace,
        status,
        step_id="probe",
        overall_percent=20,
        remaining_steps=["transcribe", "plan", "render", "ops", "validate"],
        message="Machine check completed",
        estimate=estimate,
    )

    if profile["verdict"] == "blocked":
        status = transition_status(status, "failed", "preflight blocked further processing")
        save_status(workspace.status_path, status)
        print_json(
            {
                "job_id": workspace.job_id,
                "source": {
                    "kind": status["source"]["kind"],
                    "platform": status["source"].get("platform"),
                    "origin_url": status["source"].get("origin_url"),
                    "input_video_path": status["source"].get("input_video_path"),
                    "download_status": status["source"].get("download_status"),
                },
                "duration_sec": normalized["duration_sec"],
                "size_bytes": normalized["size_bytes"],
                "audio_present": normalized["audio"]["present"],
                "preflight_verdict": profile["verdict"],
                "blocking_reasons": profile["blocking_reasons"],
                "warnings": profile["warnings"],
                "estimated_minutes": estimate["total_estimated_minutes"],
                "next_action": next_action(status),
            }
        )
        return 0

    status = transition_status(status, "probed", "video metadata collected")
    status = transition_status(status, "awaiting_template_confirmation", "waiting for user confirmation")
    save_status(workspace.status_path, status)

    print_json(
        {
            "job_id": workspace.job_id,
            "source": {
                "kind": status["source"]["kind"],
                "platform": status["source"].get("platform"),
                "origin_url": status["source"].get("origin_url"),
                "input_video_path": status["source"].get("input_video_path"),
                "download_status": status["source"].get("download_status"),
            },
            "duration_sec": normalized["duration_sec"],
            "size_bytes": normalized["size_bytes"],
            "audio_present": normalized["audio"]["present"],
            "preflight_verdict": profile["verdict"],
            "execution_profile": profile,
            "estimated_minutes": estimate["total_estimated_minutes"],
            "next_action": next_action(status),
        }
    )
    return 0


def cmd_confirm_template(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    require_phase(status, {"awaiting_template_confirmation"}, "confirm template")
    template_id = validate_template_id(resolve_template(args.template))
    status = confirm_template(
        status,
        template_id=template_id,
        length_mode=args.length_mode,
        target_seconds=args.target_seconds,
        transcription_mode=args.transcription_mode,
        diarization_mode=args.diarization_mode,
    )
    status = transition_status(status, "confirmed_for_transcription", "template confirmed by user")
    save_status(workspace.status_path, status)
    print_json({"job_id": workspace.job_id, "phase": status["phase"]})
    return 0


def cmd_transcribe(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    require_phase(status, {"confirmed_for_transcription"}, "transcribe video")
    video_path = Path(status["source"]["input_video_path"])
    estimate = read_json(workspace.probe_dir / "estimate.json") if (workspace.probe_dir / "estimate.json").exists() else None
    profile = status.get("execution_profile") or read_json(workspace.probe_dir / "execution_profile.json")

    detail = f"using {profile['asr_backend']} {profile['asr_model']} on {profile['device'].upper()}"
    status = _start_progress_step(
        workspace,
        status,
        step_id="transcribe",
        estimate=estimate,
        overall_percent=25,
        remaining_steps=["transcribe", "plan", "render", "ops"],
        detail=detail,
    )
    status = transition_status(status, "transcribing", "audio extraction and transcription started")
    save_status(workspace.status_path, status)

    audio_path = workspace.audio_dir / "extracted.wav"
    extract_audio(video_path, audio_path)
    outputs = transcribe_audio(
        audio_path,
        workspace.transcript_dir,
        template_id=status["template"]["confirmed"] or status["template"]["suggested"],
        language_hint=status["preferences"]["language_hint"],
        model_name=profile["asr_model"],
        device=profile["device"],
        compute_type=profile["compute_type"],
    )

    diarization_segments = None
    if profile["diarization_enabled"]:
        diarization_path = workspace.diarization_dir / "speakers.json"
        diarize_audio(audio_path, diarization_path)
        diarization_payload = read_json(diarization_path)
        diarization_segments = diarization_payload["segments"]
        status = mark_artifact(status, "diarization", relative_to_job(workspace.root, diarization_path))

    transcript_payload = read_json(Path(outputs["segments"]))
    utterances = build_utterances(transcript_payload["segments"], diarization_segments)
    utterances_path = workspace.transcript_dir / "utterances.json"
    write_utterances(utterances_path, utterances)

    status = mark_artifact(status, "audio", relative_to_job(workspace.root, audio_path))
    status = mark_artifact(status, "transcript_segments", relative_to_job(workspace.root, Path(outputs["segments"])))
    status = mark_artifact(status, "transcript_text", relative_to_job(workspace.root, Path(outputs["text"])))
    status = mark_artifact(status, "transcript_srt", relative_to_job(workspace.root, Path(outputs["srt"])))
    status = mark_artifact(status, "transcript_vtt", relative_to_job(workspace.root, Path(outputs["vtt"])))
    status = mark_artifact(status, "utterances", relative_to_job(workspace.root, utterances_path))
    status = transition_status(status, "transcribed", "transcription artifacts created")
    status = _finish_progress_step(
        workspace,
        status,
        step_id="transcribe",
        overall_percent=55,
        remaining_steps=["plan", "render", "ops", "validate"],
        message="Transcription completed",
        estimate=estimate,
    )
    save_status(workspace.status_path, status)

    print_json({"job_id": workspace.job_id, "phase": status["phase"], "next_action": next_action(status)})
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    require_phase(status, {"transcribed", "analysis_ready"}, "plan clips")
    estimate = read_json(workspace.probe_dir / "estimate.json") if (workspace.probe_dir / "estimate.json").exists() else None
    template_id = status["template"]["confirmed"] or status["template"]["suggested"]
    profile = status.get("execution_profile") or read_json(workspace.probe_dir / "execution_profile.json")

    detail = "building ranked clip candidates from prepared transcript data"
    if profile.get("diarization_enabled"):
        detail = "building ranked clip candidates from transcript and speaker data"
    status = _start_progress_step(
        workspace,
        status,
        step_id="plan",
        estimate=estimate,
        overall_percent=60,
        remaining_steps=["plan", "render", "ops"],
        detail=detail,
    )

    decision = decide_diarization(template_id, status["preferences"]["diarization_mode"])
    decision["enabled"] = bool(profile.get("diarization_enabled"))
    decision["reason"] = profile.get("diarization_reason", decision["reason"])
    decision_path = workspace.planning_dir / "template_decision.json"
    write_template_decision(decision_path, decision)
    status = mark_artifact(status, "template_decision", relative_to_job(workspace.root, decision_path))

    utterances_payload = read_json(workspace.transcript_dir / "utterances.json")
    transcript_segments = utterances_payload["utterances"]
    candidates = build_segment_candidates(
        transcript_segments,
        template_id=template_id,
        length_mode=status["preferences"]["length_mode"],
        target_seconds=status["preferences"]["target_seconds"],
    )
    scored = score_candidates(candidates, template_id)
    clip_plan = build_clip_plan(
        job_id=workspace.job_id,
        template_id=template_id,
        length_policy=status["preferences"]["length_mode"],
        scored_candidates=scored,
        max_clips=args.max_clips,
    )
    plan_outputs = write_plan_outputs(workspace.planning_dir, clip_plan=clip_plan, segment_candidates=scored)

    status = mark_artifact(status, "segment_candidates", relative_to_job(workspace.root, plan_outputs["candidates"]))
    status = mark_artifact(status, "clip_plan", relative_to_job(workspace.root, plan_outputs["clip_plan"]))
    status = transition_status(status, "analysis_ready", "clip analysis complete")
    status = transition_status(status, "awaiting_plan_confirmation", "waiting for clip plan approval")
    status = _finish_progress_step(
        workspace,
        status,
        step_id="plan",
        overall_percent=75,
        remaining_steps=["render", "ops", "validate"],
        message="Clip planning completed",
        estimate=estimate,
    )
    save_status(workspace.status_path, status)

    print_json({"job_id": workspace.job_id, "phase": status["phase"], "clip_plan": str(plan_outputs["clip_plan"])})
    return 0


def cmd_approve_plan(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    require_phase(status, {"awaiting_plan_confirmation"}, "approve clip plan")
    status = confirm_plan(status)
    status = transition_status(status, "approved_for_render", "clip plan approved by user")
    save_status(workspace.status_path, status)
    print_json({"job_id": workspace.job_id, "phase": status["phase"]})
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    require_phase(status, {"approved_for_render"}, "render clips")
    estimate = read_json(workspace.probe_dir / "estimate.json") if (workspace.probe_dir / "estimate.json").exists() else None
    status = _start_progress_step(
        workspace,
        status,
        step_id="render",
        estimate=estimate,
        overall_percent=80,
        remaining_steps=["render", "ops"],
        detail="exporting clip files",
    )
    status = transition_status(status, "rendering", "clip rendering started")
    save_status(workspace.status_path, status)

    clip_plan = read_json(workspace.planning_dir / "clip_plan.v1.json")
    source_video = Path(status["source"]["input_video_path"])
    rendered = []
    clip_artifact_dir = workspace.planning_dir / "clip_artifacts"
    for clip in clip_plan["clips"]:
        artifact_paths = render_clip(
            source_video,
            workspace.clips_dir,
            clip_artifact_dir,
            sequence=clip["sequence"],
            title=clip["title"],
            stem=clip["output_stem"],
            start_sec=clip["start_sec"],
            end_sec=clip["end_sec"],
        )
        rendered.append({**clip, **artifact_paths})

    status = transition_status(status, "ops_generating", "render complete, generating publish assets next")
    status = _finish_progress_step(
        workspace,
        status,
        step_id="render",
        overall_percent=90,
        remaining_steps=["ops", "validate"],
        message="Clip rendering completed",
        estimate=estimate,
    )
    save_status(workspace.status_path, status)
    print_json(
        {
            "job_id": workspace.job_id,
            "rendered_clip_count": len(rendered),
            "phase": status["phase"],
            "next_action": next_action(status),
        }
    )
    return 0


def cmd_ops(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    require_phase(status, {"ops_generating"}, "generate publish assets")
    estimate = read_json(workspace.probe_dir / "estimate.json") if (workspace.probe_dir / "estimate.json").exists() else None
    status = _start_progress_step(
        workspace,
        status,
        step_id="ops",
        estimate=estimate,
        overall_percent=92,
        remaining_steps=["ops", "validate"],
        detail="writing publish copy and manifest",
    )
    clip_plan = read_json(workspace.planning_dir / "clip_plan.v1.json")
    template_id = clip_plan["template"]

    publish_rows = []
    manifest_rows = []
    for clip in clip_plan["clips"]:
        payload = build_publish_copy(
            template_id,
            clip["topic"],
            clip["title"],
            guest_name=args.guest_name,
            volume_label=getattr(args, "volume_label", None),
        )
        clip_file = f"{clip['output_stem']}.mp4"
        publish_rows.append(
            {
                "sequence": clip["sequence"],
                "headline": payload["headline"],
                "clip_file": clip_file,
                "short_hook": payload["short_hook"],
                "description": payload["description"],
                "hashtags": payload["hashtags"],
                "cta": payload["cta"],
                "platform_variants": payload["platform_variants"],
                "editor_notes": payload["editor_notes"],
            }
        )
        manifest_rows.append(
            {
                "sequence": clip["sequence"],
                "headline": payload["headline"],
                "clip_file": clip_file,
            }
        )

    write_publish_copy(workspace.ops_dir, publish_rows)
    operations_manual_path = write_operations_manual(workspace.ops_dir, publish_rows)

    transcript_text_path = workspace.root / status["artifacts"]["transcript_text"]
    utterances_path = workspace.root / status["artifacts"]["utterances"]
    transcript_text = transcript_text_path.read_text(encoding="utf-8") if transcript_text_path.exists() else ""
    utterances_payload = read_json(utterances_path) if utterances_path.exists() else {"utterances": []}
    article = build_full_article(
        job_id=workspace.job_id,
        title=args.article_title or clip_plan["clips"][0]["title"],
        template_id=template_id,
        transcript_text=transcript_text,
        utterances=utterances_payload.get("utterances", []),
        host_name=args.host_name,
        guest_name=args.guest_name,
    )
    article_assets = write_full_article_assets(workspace.ops_dir, article)

    manifest_path = write_publish_manifest(workspace.ops_dir, manifest_rows, article_assets, operations_manual_path)
    status = mark_artifact(status, "publish_manifest", relative_to_job(workspace.root, manifest_path))
    status = mark_artifact(status, "operations_manual", relative_to_job(workspace.root, operations_manual_path))
    status = mark_artifact(status, "full_article_markdown", relative_to_job(workspace.root, article_assets["md"]))
    status = mark_artifact(status, "full_article_docx", relative_to_job(workspace.root, article_assets["docx"]))
    status = mark_artifact(status, "full_article_pdf", relative_to_job(workspace.root, article_assets["pdf"]))
    status = transition_status(status, "validating", "ops package generated, validating outputs next")
    status = _finish_progress_step(
        workspace,
        status,
        step_id="ops",
        overall_percent=96,
        remaining_steps=["validate"],
        message="Publish package generation completed",
        estimate=estimate,
    )
    save_status(workspace.status_path, status)
    print_json(
        {
            "job_id": workspace.job_id,
            "phase": status["phase"],
            "next_action": next_action(status),
            "publish_manifest": str(manifest_path),
            "operations_manual": str(operations_manual_path),
            "full_article_markdown": str(article_assets["md"]),
            "full_article_docx": str(article_assets["docx"]),
            "full_article_pdf": str(article_assets["pdf"]),
        }
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    require_phase(status, {"validating"}, "validate outputs")
    estimate = read_json(workspace.probe_dir / "estimate.json") if (workspace.probe_dir / "estimate.json").exists() else None
    status = _start_progress_step(
        workspace,
        status,
        step_id="validate",
        estimate=estimate,
        overall_percent=97,
        remaining_steps=["validate"],
        detail="checking copy quality and clip playback integrity",
    )
    save_status(workspace.status_path, status)

    clip_plan = read_json(workspace.planning_dir / "clip_plan.v1.json")
    publish_copy_path = workspace.ops_dir / "publish_copy.json"
    article_markdown_path = workspace.ops_dir / "full_article.md"
    copy_report = validate_publish_outputs(
        clip_plan=clip_plan,
        publish_copy_path=publish_copy_path,
        article_markdown_path=article_markdown_path,
    )
    clip_report = validate_clips(clips_dir=workspace.clips_dir, clip_plan=clip_plan)
    issues = list(copy_report["issues"]) + list(clip_report["issues"])
    validation_payload = {
        "passed": not issues,
        "copy": copy_report,
        "clips": clip_report,
        "issues": issues,
    }
    report_path = write_validation_report(workspace.ops_dir / "validation_report.json", validation_payload)
    status = mark_artifact(status, "validation_report", relative_to_job(workspace.root, report_path))
    if issues:
        status = record_error(status, "output validation failed")
        status = transition_status(status, "failed", "output validation failed")
        save_status(workspace.status_path, status)
        print_json(
            {
                "job_id": workspace.job_id,
                "phase": status["phase"],
                "validation_report": str(report_path),
                "issues": issues,
            }
        )
        return 1

    status = transition_status(status, "completed", "output validation passed")
    status = _finish_progress_step(
        workspace,
        status,
        step_id="validate",
        overall_percent=100,
        remaining_steps=[],
        message="Output validation completed",
        estimate=estimate,
    )
    save_status(workspace.status_path, status)
    print_json(
        {
            "job_id": workspace.job_id,
            "phase": status["phase"],
            "validation_report": str(report_path),
        }
    )
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    workspace, status = _load_workspace_status(args.job_id, args)
    progress = status.get("progress", {})
    current_step = progress.get("current_step", {})
    print_json(
        {
            "job_id": workspace.job_id,
            "phase": status["phase"],
            "next_action": next_action(status),
            "status_path": str(workspace.status_path),
            "preflight_verdict": status.get("preflight", {}).get("verdict"),
            "current_step": current_step,
            "eta_seconds_remaining": progress.get("eta_seconds_remaining"),
        }
    )
    return 0


def print_json(payload: dict[str, Any]) -> None:
    import json

    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> int:
    args = parse_args()
    try:
        if args.command != "resume":
            _check_required_dependencies(args.command, args)
        return args.func(args)
    except StatusError as exc:
        if getattr(args, "job_id", None):
            workspace = get_job_workspace(args.job_id, _resolve_workspace_dir(args))
            if workspace.status_path.exists():
                status = load_status(workspace.status_path)
                status = record_error(status, str(exc))
                save_status(workspace.status_path, status)
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
