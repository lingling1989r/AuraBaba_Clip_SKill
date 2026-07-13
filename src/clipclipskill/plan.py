from __future__ import annotations

from pathlib import Path
from typing import Any

from .ops_copy import build_structured_title
from .workspace import clip_output_stem, write_json, write_text


def build_clip_plan(
    *,
    job_id: str,
    template_id: str,
    length_policy: str,
    scored_candidates: list[dict[str, Any]],
    max_clips: int = 3,
) -> dict[str, Any]:
    clips = []
    for idx, candidate in enumerate(scored_candidates[:max_clips], start=1):
        topic = candidate["topic"]
        output_stem = clip_output_stem(idx, topic)
        title = build_structured_title(template_id, topic)
        clips.append(
            {
                "sequence": idx,
                "slug": output_stem,
                "title": title,
                "start_sec": candidate["start_sec"],
                "end_sec": candidate["end_sec"],
                "duration_sec": candidate["duration_sec"],
                "topic": topic,
                "score": candidate["score"],
                "source_utterance_ids": candidate.get("source_utterance_ids", []),
                "quality_flags": candidate.get("quality_flags", []),
                "diarization_used": bool(candidate.get("speakers")),
                "confidence_band": "high" if candidate["score"]["total"] >= 0.82 else "medium",
                "rationale": [
                    "主题相对完整",
                    "可独立理解",
                    f"符合 {template_id} 模板优先级",
                ],
                "requires_manual_review": candidate["duration_sec"] < 15 or bool(candidate.get("quality_flags")),
                "output_stem": output_stem,
            }
        )

    return {
        "schema_version": "1.0",
        "job_id": job_id,
        "template": template_id,
        "length_policy": length_policy,
        "clips": clips,
    }


def write_plan_outputs(
    planning_dir: Path,
    *,
    clip_plan: dict[str, Any],
    segment_candidates: list[dict[str, Any]],
) -> dict[str, Path]:
    candidates_path = planning_dir / "segment_candidates.v1.json"
    clip_plan_path = planning_dir / "clip_plan.v1.json"
    summary_path = planning_dir / "plan_summary.md"
    checklist_path = planning_dir / "review_checklist.md"

    write_json(candidates_path, {"candidates": segment_candidates})
    write_json(clip_plan_path, clip_plan)

    summary_lines = [
        "# Clip Plan Summary",
        "",
        f"Template: `{clip_plan['template']}`",
        f"Length policy: `{clip_plan['length_policy']}`",
        "",
    ]
    for clip in clip_plan["clips"]:
        summary_lines.append(
            f"- {clip['sequence']:03d} `{clip['title']}` {clip['start_sec']}s → {clip['end_sec']}s"
        )
    write_text(summary_path, "\n".join(summary_lines) + "\n")

    checklist = """# Review Checklist

- Confirm each clip topic is correct
- Confirm each clip boundary is acceptable
- Confirm the ordering is acceptable
- Confirm whether any clip should be removed before render
"""
    write_text(checklist_path, checklist)

    return {
        "candidates": candidates_path,
        "clip_plan": clip_plan_path,
        "summary": summary_path,
        "checklist": checklist_path,
    }
