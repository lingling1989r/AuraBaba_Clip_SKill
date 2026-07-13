from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import write_json


def _speaker_for_segment(segment: dict[str, Any], diarization_segments: list[dict[str, Any]]) -> str | None:
    start = float(segment["start"])
    end = float(segment["end"])
    best_speaker = None
    best_overlap = 0.0
    for diarization_segment in diarization_segments:
        diar_start = float(diarization_segment["start"])
        diar_end = float(diarization_segment["end"])
        overlap = max(0.0, min(end, diar_end) - max(start, diar_start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = diarization_segment["speaker"]
    return best_speaker


def build_utterances(
    transcript_segments: list[dict[str, Any]],
    diarization_segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    diarization_segments = diarization_segments or []
    utterances = []
    for index, segment in enumerate(transcript_segments, start=1):
        speaker = segment.get("speaker") or _speaker_for_segment(segment, diarization_segments)
        utterances.append(
            {
                "utterance_id": f"utt_{index:04d}",
                "segment_id": segment.get("id", index),
                "start": round(float(segment["start"]), 3),
                "end": round(float(segment["end"]), 3),
                "text": segment["text"],
                "speaker": speaker,
                "avg_logprob": float(segment.get("avg_logprob", 0.0)),
                "no_speech_prob": float(segment.get("no_speech_prob", 0.0)),
            }
        )
    return utterances


def write_utterances(output_path: Path, utterances: list[dict[str, Any]]) -> Path:
    write_json(output_path, {"utterances": utterances})
    return output_path
