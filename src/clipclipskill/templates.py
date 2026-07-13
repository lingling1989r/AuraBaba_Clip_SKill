from __future__ import annotations

from pathlib import Path
from typing import Any

from .workspace import REPO_ROOT, read_json

TEMPLATES_DIR = REPO_ROOT / "templates" / "content_types"

TEMPLATE_IDS = {
    "podcast_interview",
    "solo_course",
    "gaming_livestream",
    "sports_highlights",
}


class TemplateError(RuntimeError):
    pass


def list_template_ids() -> list[str]:
    return sorted(TEMPLATE_IDS)


def validate_template_id(template_id: str) -> str:
    if template_id not in TEMPLATE_IDS:
        raise TemplateError(f"unknown template_id: {template_id}")
    return template_id


def load_template(template_id: str) -> dict[str, Any]:
    validate_template_id(template_id)
    template_path = TEMPLATES_DIR / f"{template_id}.json"
    if not template_path.exists():
        raise TemplateError(f"missing template file: {template_path}")
    return read_json(template_path)


def resolve_template(template_hint: str | None) -> str:
    if not template_hint:
        return "solo_course"
    hint = template_hint.strip().lower()
    aliases = {
        "podcast": "podcast_interview",
        "interview": "podcast_interview",
        "访谈": "podcast_interview",
        "播客": "podcast_interview",
        "course": "solo_course",
        "class": "solo_course",
        "知识": "solo_course",
        "课程": "solo_course",
        "gaming": "gaming_livestream",
        "game": "gaming_livestream",
        "直播": "gaming_livestream",
        "sports": "sports_highlights",
        "sport": "sports_highlights",
        "football": "sports_highlights",
        "soccer": "sports_highlights",
        "体育": "sports_highlights",
    }
    return aliases.get(hint, hint)


def diarization_default(template_id: str) -> bool:
    template = load_template(template_id)
    return bool(template.get("diarization_default", False))
