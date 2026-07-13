from __future__ import annotations

from typing import Any

from .templates import load_template


def _topic_from_text(text: str, fallback: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return fallback
    for sep in ("。", "？", "！", "，", ".", "?", "!", ","):
        if sep in cleaned:
            cleaned = cleaned.split(sep, 1)[0].strip()
            break
    return cleaned or fallback


def _close_candidate(
    candidates: list[dict[str, Any]],
    batch: list[dict[str, Any]],
    *,
    template_id: str,
    length_mode: str,
    target_seconds: int | None,
) -> None:
    if not batch:
        return
    start = float(batch[0]["start"])
    end = float(batch[-1]["end"])
    duration = round(end - start, 2)
    transcript_excerpt = " ".join(item["text"].strip() for item in batch if item["text"].strip())
    source_utterance_ids = [item.get("utterance_id") or f"segment_{index + 1}" for index, item in enumerate(batch)]
    speakers = [item.get("speaker") for item in batch if item.get("speaker")]
    unique_speakers = sorted(set(speakers))
    candidates.append(
        {
            "sequence": len(candidates) + 1,
            "topic": _topic_from_text(transcript_excerpt, f"片段{len(candidates) + 1}"),
            "start_sec": start,
            "end_sec": end,
            "duration_sec": duration,
            "transcript_excerpt": transcript_excerpt,
            "template_id": template_id,
            "length_mode": length_mode,
            "target_seconds": target_seconds,
            "source_utterance_ids": source_utterance_ids,
            "speaker_count": len(unique_speakers),
            "speakers": unique_speakers,
            "avg_logprob": round(
                sum(float(item.get("avg_logprob", 0.0)) for item in batch) / len(batch),
                4,
            ),
            "avg_no_speech_prob": round(
                sum(float(item.get("no_speech_prob", 0.0)) for item in batch) / len(batch),
                4,
            ),
        }
    )


def build_segment_candidates(
    transcript_segments: list[dict[str, Any]],
    *,
    template_id: str,
    length_mode: str,
    target_seconds: int | None,
) -> list[dict[str, Any]]:
    template = load_template(template_id)
    defaults = template["length_defaults"]
    preferred_min = int(target_seconds or defaults["preferred_min_sec"])
    hard_max = int(max(target_seconds or defaults["preferred_max_sec"], defaults["hard_max_sec"]))

    candidates: list[dict[str, Any]] = []
    batch: list[dict[str, Any]] = []
    current_speakers: set[str] = set()

    for segment in transcript_segments:
        batch.append(segment)
        if segment.get("speaker"):
            current_speakers.add(str(segment["speaker"]))
        duration = float(batch[-1]["end"]) - float(batch[0]["start"])
        text = str(segment.get("text", "")).strip()
        speaker_turn_boundary = bool(segment.get("speaker")) and len(current_speakers) > 1
        punctuation_boundary = text.endswith(("。", "？", "！", ".", "?", "!"))
        should_close = duration >= preferred_min and (punctuation_boundary or speaker_turn_boundary)
        if duration >= hard_max:
            should_close = True
        if should_close:
            _close_candidate(
                candidates,
                batch,
                template_id=template_id,
                length_mode=length_mode,
                target_seconds=target_seconds,
            )
            batch = []
            current_speakers = set()

    _close_candidate(
        candidates,
        batch,
        template_id=template_id,
        length_mode=length_mode,
        target_seconds=target_seconds,
    )
    return candidates
