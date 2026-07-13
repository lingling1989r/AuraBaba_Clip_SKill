from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import ensure_dir, write_json, write_text


DEFAULT_BEAM_SIZE = 5


def format_timestamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def build_stub_segments(template_id: str) -> list[dict[str, Any]]:
    base = {
        "podcast_interview": [
            (0.0, 32.0, "主持人抛出一个核心问题，嘉宾开始给出完整观点。"),
            (32.0, 78.0, "嘉宾展开解释，并给出一个值得单独成片的洞察。"),
            (78.0, 126.0, "主持人追问后，嘉宾补上案例与结论。"),
        ],
        "solo_course": [
            (0.0, 48.0, "老师抛出今天要讲的概念，并解释为什么重要。"),
            (48.0, 104.0, "老师给出定义和使用场景。"),
            (104.0, 168.0, "老师用一个例子讲透知识点，并做小结。"),
        ],
        "gaming_livestream": [
            (0.0, 18.0, "主播发现局势不对，开始准备一波关键操作。"),
            (18.0, 42.0, "高能操作完成，主播情绪明显拉高。"),
            (42.0, 68.0, "观众能独立看懂的反应和结果反馈出现。"),
        ],
        "sports_highlights": [
            (0.0, 14.0, "解说铺垫进攻推进，比赛节奏提升。"),
            (14.0, 30.0, "关键事件发生，解说情绪和现场气氛到顶点。"),
            (30.0, 52.0, "事件后的即时反应和结果确认完成闭环。"),
        ],
    }
    rows = base.get(template_id, base["solo_course"])
    return [
        {
            "id": index + 1,
            "start": start,
            "end": end,
            "text": text,
            "speaker": None,
            "avg_logprob": -0.2,
            "no_speech_prob": 0.05,
            "words": [],
        }
        for index, (start, end, text) in enumerate(rows)
    ]


def _normalize_language(language_hint: str) -> str | None:
    hint = (language_hint or "auto").strip().lower()
    if hint in {"", "auto", "detect"}:
        return None
    aliases = {
        "zh-cn": "zh",
        "zh-hans": "zh",
        "zh-hant": "zh",
        "english": "en",
        "chinese": "zh",
    }
    return aliases.get(hint, hint)


def _load_whisper_model(model_name: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed") from exc
    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _normalize_word(word: Any) -> dict[str, Any]:
    return {
        "start": None if getattr(word, "start", None) is None else round(float(word.start), 3),
        "end": None if getattr(word, "end", None) is None else round(float(word.end), 3),
        "word": str(getattr(word, "word", "")).strip(),
        "probability": None if getattr(word, "probability", None) is None else round(float(word.probability), 4),
    }


def _normalize_segment(segment: Any, segment_id: int) -> dict[str, Any]:
    words = [_normalize_word(word) for word in (getattr(segment, "words", None) or [])]
    return {
        "id": segment_id,
        "start": round(float(segment.start), 3),
        "end": round(float(segment.end), 3),
        "text": str(segment.text).strip(),
        "speaker": None,
        "avg_logprob": round(float(getattr(segment, "avg_logprob", 0.0)), 4),
        "no_speech_prob": round(float(getattr(segment, "no_speech_prob", 0.0)), 4),
        "words": words,
    }


def transcribe_with_faster_whisper(
    audio_path: Path,
    *,
    model_name: str,
    language_hint: str,
    device: str,
    compute_type: str,
) -> dict[str, Any]:
    model = _load_whisper_model(model_name, device, compute_type)
    segments_iter, info = model.transcribe(
        str(audio_path),
        beam_size=DEFAULT_BEAM_SIZE,
        vad_filter=True,
        word_timestamps=True,
        language=_normalize_language(language_hint),
    )
    segments = [_normalize_segment(segment, index + 1) for index, segment in enumerate(segments_iter)]
    if not segments:
        raise RuntimeError("transcription produced no segments")
    detected_language = getattr(info, "language", None) or language_hint or "auto"
    return {
        "engine": "faster-whisper",
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "language_hint": language_hint,
        "detected_language": detected_language,
        "audio_path": str(audio_path),
        "segments": segments,
    }


def segments_to_text(segments: list[dict[str, Any]]) -> str:
    return "\n".join(segment["text"] for segment in segments)


def segments_to_srt(segments: list[dict[str, Any]]) -> str:
    blocks = []
    for idx, segment in enumerate(segments, start=1):
        blocks.append(
            "\n".join(
                [
                    str(idx),
                    f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}",
                    segment["text"],
                ]
            )
        )
    return "\n\n".join(blocks) + "\n"


def segments_to_vtt(segments: list[dict[str, Any]]) -> str:
    blocks = ["WEBVTT\n"]
    for segment in segments:
        start = format_timestamp(segment["start"]).replace(",", ".")
        end = format_timestamp(segment["end"]).replace(",", ".")
        blocks.append(f"{start} --> {end}\n{segment['text']}\n")
    return "\n".join(blocks)


def transcribe_audio(
    audio_path: Path,
    output_dir: Path,
    *,
    template_id: str,
    language_hint: str = "auto",
    model_name: str = "medium",
    device: str = "cpu",
    compute_type: str = "int8",
    allow_stub_fallback: bool = False,
) -> dict[str, str]:
    ensure_dir(output_dir)
    try:
        payload = transcribe_with_faster_whisper(
            audio_path,
            model_name=model_name,
            language_hint=language_hint,
            device=device,
            compute_type=compute_type,
        )
    except Exception:
        if not allow_stub_fallback:
            raise
        payload = {
            "engine": "stub-whisper",
            "model": model_name,
            "device": device,
            "compute_type": compute_type,
            "language_hint": language_hint,
            "detected_language": language_hint,
            "audio_path": str(audio_path),
            "segments": build_stub_segments(template_id),
        }

    segments = payload["segments"]
    segments_path = output_dir / "whisper.segments.json"
    transcript_path = output_dir / "transcript.txt"
    srt_path = output_dir / "transcript.srt"
    vtt_path = output_dir / "transcript.vtt"

    write_json(segments_path, payload)
    write_text(transcript_path, segments_to_text(segments) + "\n")
    write_text(srt_path, segments_to_srt(segments))
    write_text(vtt_path, segments_to_vtt(segments))

    return {
        "segments": str(segments_path),
        "text": str(transcript_path),
        "srt": str(srt_path),
        "vtt": str(vtt_path),
    }
