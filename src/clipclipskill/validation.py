from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .workspace import write_json

FORBIDDEN_COPY_SNIPPETS = [
    "thinking",
    "reasoning",
    "chain of thought",
    "internal monologue",
    "推理过程",
    "思考过程",
    "处理中",
    "file name",
    "filename",
    ".mp4",
    ".srt",
    ".json",
]

FORBIDDEN_HEADLINE_SNIPPETS = [
    "参数",
    "提示词",
    "工作流",
    "向量数据库",
]

HEADLINE_MIN_LENGTH = 12
HEADLINE_MAX_LENGTH = 60


def validate_publish_outputs(
    *,
    clip_plan: dict[str, Any],
    publish_copy_path: Path,
    article_markdown_path: Path,
) -> dict[str, Any]:
    issues: list[str] = []
    topic_text = " ".join(str(clip.get("topic") or "") for clip in clip_plan.get("clips", []))
    normalized_topics = _normalize_text(topic_text)

    publish_copy = _load_json(publish_copy_path)
    clip_rows = publish_copy.get("clips", []) if isinstance(publish_copy, dict) else []
    for row in clip_rows:
        headline = str(row.get("headline") or "")
        description = str(row.get("description") or "")
        short_hook = str(row.get("short_hook") or "")
        issues.extend(_check_headline(headline, prefix=f"clip {row.get('sequence', '?')}: "))
        combined = " ".join([headline, description, short_hook])
        issues.extend(_check_copy_text(combined, normalized_topics, prefix=f"clip {row.get('sequence', '?')}: "))

    article_markdown = article_markdown_path.read_text(encoding="utf-8") if article_markdown_path.exists() else ""
    issues.extend(_check_copy_text(article_markdown, normalized_topics, prefix="full article: "))

    return {
        "passed": not issues,
        "issues": issues,
        "checked_files": {
            "publish_copy": str(publish_copy_path),
            "full_article_markdown": str(article_markdown_path),
        },
    }


def validate_clips(*, clips_dir: Path, clip_plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    checked: list[str] = []

    for clip in clip_plan.get("clips", []):
        clip_path = clips_dir / f"{clip['output_stem']}.mp4"
        checked.append(str(clip_path))
        if not clip_path.exists():
            issues.append(f"missing clip file: {clip_path.name}")
            continue
        ffprobe_report = _probe_video_stream(clip_path)
        if ffprobe_report["status"] != "ok":
            issues.append(f"{clip_path.name}: {ffprobe_report['message']}")
            continue
        if ffprobe_report["video_stream_count"] != 1:
            issues.append(f"{clip_path.name}: expected exactly one video stream")
        if ffprobe_report["avg_frame_rate"] <= 0:
            issues.append(f"{clip_path.name}: invalid frame rate")
        if ffprobe_report["duration_sec"] <= 0:
            issues.append(f"{clip_path.name}: invalid duration")
        if ffprobe_report["has_audio"] is False:
            issues.append(f"{clip_path.name}: audio stream missing")
        if ffprobe_report["video_codec"] is None:
            issues.append(f"{clip_path.name}: video codec missing")
        if ffprobe_report["video_codec"] not in {None, "h264"}:
            issues.append(f"{clip_path.name}: video codec may be incompatible with QuickTime")
        if ffprobe_report["audio_codec"] not in {None, "aac"}:
            issues.append(f"{clip_path.name}: audio codec may be incompatible with QuickTime")
        if ffprobe_report["pixel_format"] not in {None, "yuv420p"}:
            issues.append(f"{clip_path.name}: pixel format may be incompatible with QuickTime")
        if ffprobe_report["video_duration_sec"] > 0 and ffprobe_report["audio_duration_sec"] > 0:
            drift = abs(ffprobe_report["video_duration_sec"] - ffprobe_report["audio_duration_sec"])
            if drift > 0.35:
                issues.append(f"{clip_path.name}: audio/video duration drift is too large")
        if ffprobe_report["estimated_speed_ratio"] > 0 and not 0.95 <= ffprobe_report["estimated_speed_ratio"] <= 1.05:
            issues.append(f"{clip_path.name}: playback speed appears inconsistent with planned duration")

    return {
        "passed": not issues,
        "issues": issues,
        "checked_files": checked,
    }


def write_validation_report(report_path: Path, payload: dict[str, Any]) -> Path:
    write_json(report_path, payload)
    return report_path


def _check_copy_text(text: str, normalized_topics: str, *, prefix: str) -> list[str]:
    issues: list[str] = []
    normalized_text = _normalize_text(text)
    if not normalized_text:
        issues.append(prefix + "content is empty")
        return issues
    if normalized_topics and not any(topic in normalized_text for topic in normalized_topics.split() if topic):
        issues.append(prefix + "content appears off-topic")
    for snippet in FORBIDDEN_COPY_SNIPPETS:
        if snippet.lower() in normalized_text:
            issues.append(prefix + f"contains forbidden process text: {snippet}")
    return issues


def _check_headline(headline: str, *, prefix: str) -> list[str]:
    issues: list[str] = []
    normalized_headline = _normalize_text(headline)
    visible_headline = "".join(str(headline).split())
    if not normalized_headline:
        issues.append(prefix + "headline is empty")
        return issues
    if len(visible_headline) < HEADLINE_MIN_LENGTH or len(visible_headline) > HEADLINE_MAX_LENGTH:
        issues.append(prefix + "headline length is out of range")
    for snippet in FORBIDDEN_HEADLINE_SNIPPETS:
        if snippet.lower() in normalized_headline:
            issues.append(prefix + f"headline contains technical jargon: {snippet}")
    return issues


def _normalize_text(text: str) -> str:
    return " ".join(str(text).lower().replace("\n", " ").split())


def _load_json(file_path: Path) -> Any:
    if not file_path.exists():
        return {}
    return json.loads(file_path.read_text(encoding="utf-8"))


def _probe_video_stream(file_path: Path) -> dict[str, Any]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,avg_frame_rate,pix_fmt,duration",
        "-of",
        "json",
        str(file_path),
    ]
    empty_report = {
        "video_stream_count": 0,
        "avg_frame_rate": 0.0,
        "duration_sec": 0.0,
        "has_audio": None,
        "video_codec": None,
        "audio_codec": None,
        "pixel_format": None,
        "video_duration_sec": 0.0,
        "audio_duration_sec": 0.0,
        "estimated_speed_ratio": 0.0,
    }
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        return {
            "status": "unavailable",
            "message": "ffprobe not installed; cannot verify clip playback integrity",
            **empty_report,
        }
    except subprocess.CalledProcessError as exc:
        return {
            "status": "error",
            "message": exc.stderr.strip() or "ffprobe failed",
            **empty_report,
        }

    payload = json.loads(result.stdout or "{}")
    streams = payload.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    avg_frame_rate = _parse_frame_rate(video_streams[0].get("avg_frame_rate")) if video_streams else 0.0
    duration_sec = _parse_float(payload.get("format", {}).get("duration"))
    video_duration_sec = _parse_float(video_streams[0].get("duration")) if video_streams else 0.0
    audio_duration_sec = _parse_float(audio_streams[0].get("duration")) if audio_streams else 0.0
    reference_duration = duration_sec or max(video_duration_sec, audio_duration_sec)
    estimated_speed_ratio = 0.0
    if reference_duration > 0:
        estimated_speed_ratio = max(video_duration_sec, audio_duration_sec, reference_duration) / reference_duration
    return {
        "status": "ok",
        "message": "ok",
        "video_stream_count": len(video_streams),
        "avg_frame_rate": avg_frame_rate,
        "duration_sec": duration_sec,
        "has_audio": bool(audio_streams),
        "video_codec": video_streams[0].get("codec_name") if video_streams else None,
        "audio_codec": audio_streams[0].get("codec_name") if audio_streams else None,
        "pixel_format": video_streams[0].get("pix_fmt") if video_streams else None,
        "video_duration_sec": video_duration_sec,
        "audio_duration_sec": audio_duration_sec,
        "estimated_speed_ratio": estimated_speed_ratio,
    }


def _parse_frame_rate(value: Any) -> float:
    raw = str(value or "0")
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        try:
            denominator_value = float(denominator)
            if denominator_value == 0:
                return 0.0
            return float(numerator) / denominator_value
        except ValueError:
            return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _parse_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
