from __future__ import annotations

from typing import Any

from .templates import load_template


HOOK_MARKERS = ("为什么", "如何", "怎么", "关键", "终于", "绝杀", "必须", "结果", "because", "how", "why")


def _component_score(weight: float, raw_value: float) -> float:
    return round(weight * raw_value, 4)


def _duration_fit(duration: float, preferred_min: int, preferred_max: int) -> float:
    if preferred_min <= duration <= preferred_max:
        return 1.0
    if duration < preferred_min:
        return max(0.6, duration / max(preferred_min, 1))
    overflow = duration - preferred_max
    return max(0.65, 1.0 - overflow / max(preferred_max, 1))


def _hook_strength(text: str) -> float:
    lowered = text.lower()
    if any(marker in lowered for marker in HOOK_MARKERS):
        return 0.95
    return 0.78


def _clarity(candidate: dict[str, Any]) -> float:
    score = 0.86
    if candidate.get("avg_no_speech_prob", 0.0) > 0.35:
        score -= 0.18
    if candidate.get("avg_logprob", 0.0) < -0.8:
        score -= 0.12
    return max(0.55, round(score, 4))


def _energy(candidate: dict[str, Any], template_id: str) -> float:
    if template_id in {"gaming_livestream", "sports_highlights"}:
        return 0.93 if candidate["duration_sec"] >= 15 else 0.82
    return 0.78 if candidate.get("speaker_count", 1) > 1 else 0.72


def score_candidates(candidates: list[dict[str, Any]], template_id: str) -> list[dict[str, Any]]:
    template = load_template(template_id)
    weights = template.get("score_weights", {})
    preferred_min = template["length_defaults"]["preferred_min_sec"]
    preferred_max = template["length_defaults"]["preferred_max_sec"]
    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        duration = candidate["duration_sec"]
        transcript_excerpt = candidate["transcript_excerpt"]
        topic_fit = _duration_fit(duration, preferred_min, preferred_max)
        hook_strength = _hook_strength(transcript_excerpt)
        clarity = _clarity(candidate)
        novelty = 0.84
        energy = _energy(candidate, template_id)
        actionability = 0.9 if template_id == "solo_course" else 0.76
        event_significance = 0.92 if template_id == "sports_highlights" else 0.77

        components: dict[str, float] = {}
        for key, weight in weights.items():
            raw_map = {
                "topic_completeness": topic_fit,
                "hook_strength": hook_strength,
                "clarity": clarity,
                "novelty": novelty,
                "energy": energy,
                "actionability": actionability,
                "event_significance": event_significance,
            }
            components[key] = _component_score(float(weight), raw_map.get(key, 0.8))

        quality_flags = []
        if candidate.get("avg_no_speech_prob", 0.0) > 0.35:
            quality_flags.append("high_no_speech_probability")
        if duration < template["length_defaults"]["hard_min_sec"]:
            quality_flags.append("too_short")

        total = round(sum(components.values()), 4)
        scored.append(
            {
                **candidate,
                "quality_flags": quality_flags,
                "score": {"total": total, "components": components},
            }
        )

    return sorted(scored, key=lambda item: item["score"]["total"], reverse=True)
