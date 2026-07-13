from __future__ import annotations

import hashlib
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from .templates import load_template
from .workspace import REPO_ROOT, read_json, write_json, write_text

OPS_DIR = REPO_ROOT / "templates" / "ops"
EDITOR_CREDIT = "整理人：傲雪（vx:aoxueluoluo）"


def build_structured_title(template_id: str, topic: str, title: str | None = None) -> str:
    template = load_template(template_id)
    title_patterns = read_json(OPS_DIR / "short_video_title_patterns.json")
    style = str(template.get("ops_copy_style", "knowledge_takeaway"))
    style_config = title_patterns.get(style, ["{topic}"])
    fallback_title = (title or topic or "").strip()
    fallback_topic = (topic or title or "").strip() or "这个问题"

    if isinstance(style_config, list):
        pattern = style_config[0] if style_config else "{topic}"
        return _normalize_headline_length(pattern.format(topic=fallback_topic, title=fallback_title or fallback_topic))

    structures = style_config.get("structures", []) if isinstance(style_config, dict) else []
    all_patterns = [
        pattern
        for structure in structures
        if isinstance(structure, dict)
        for pattern in structure.get("patterns", [])
        if isinstance(pattern, str) and pattern.strip()
    ]
    if not structures or not all_patterns:
        return _normalize_headline_length(fallback_title or fallback_topic)

    seed = f"{template_id}|{fallback_topic}|{fallback_title}"
    digest = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    structure = structures[digest % len(structures)]
    patterns = [pattern for pattern in structure.get("patterns", []) if isinstance(pattern, str) and pattern.strip()]
    if not patterns:
        patterns = all_patterns
    pattern = patterns[(digest // max(len(structures), 1)) % len(patterns)]
    rendered = pattern.format(topic=fallback_topic, title=fallback_title or fallback_topic)
    return _normalize_headline_length(rendered)


def build_podcast_headline(
    template_id: str,
    topic: str,
    title: str,
    *,
    guest_name: str | None = None,
    volume_label: str | None = None,
) -> str:
    if template_id != "podcast_interview":
        return build_structured_title(template_id, topic, title)

    preferred_title = _normalize_headline_length((title or "").strip()) if title else ""
    main_title = preferred_title or build_structured_title(template_id, topic, title)
    lane = _build_topic_lane(topic)
    guest = (guest_name or "嘉宾").strip() or "嘉宾"
    suffix = f"对话{guest}"
    volume = (volume_label or "").strip()
    if volume:
        suffix = f"{suffix} {volume}"
    return f"{main_title}｜{lane} | {suffix}"


def build_publish_copy(
    template_id: str,
    topic: str,
    title: str,
    *,
    guest_name: str | None = None,
    volume_label: str | None = None,
) -> dict[str, Any]:
    publish_defaults = read_json(OPS_DIR / "generic_publish.json")
    hashtag_banks = read_json(OPS_DIR / "hashtag_banks.json")
    headline = build_podcast_headline(
        template_id,
        topic,
        title,
        guest_name=guest_name,
        volume_label=volume_label,
    )

    return {
        "template_id": template_id,
        "headline": headline,
        "short_hook": f"30秒看懂：{topic}",
        "description": f"这条短视频围绕“{topic}”展开，适合做独立传播。",
        "hashtags": hashtag_banks.get(template_id, []),
        "cta": publish_defaults["default_cta"],
        "platform_variants": {
            platform: {
                "title": headline,
                "description": f"{title}｜{topic}",
            }
            for platform in publish_defaults["platforms"]
        },
        "editor_notes": [
            "如需更强开头，可追加封面标题",
            "如需更完整上下文，可在描述中补充来源视频",
        ],
    }


def build_full_article(
    *,
    job_id: str,
    title: str,
    template_id: str,
    transcript_text: str,
    utterances: list[dict[str, Any]],
    host_name: str | None,
    guest_name: str | None,
) -> dict[str, Any]:
    normalized_utterances = _normalize_utterances(utterances, host_name=host_name, guest_name=guest_name)
    grouped_sections = _build_sections(normalized_utterances)
    cover_title = _build_cover_title(title, grouped_sections)
    article_markdown = _render_article_markdown(
        cover_title=cover_title,
        original_title=title,
        host_name=host_name,
        guest_name=guest_name,
        sections=grouped_sections,
        transcript_text=transcript_text,
        template_id=template_id,
    )
    return {
        "job_id": job_id,
        "template_id": template_id,
        "cover_title": cover_title,
        "original_title": title,
        "host_name": host_name,
        "guest_name": guest_name,
        "summary": _build_article_summary(grouped_sections),
        "sections": grouped_sections,
        "markdown": article_markdown,
    }


def write_publish_copy(ops_dir: Path, clips: list[dict[str, Any]]) -> dict[str, Path]:
    json_path = ops_dir / "publish_copy.json"
    md_path = ops_dir / "publish_copy.md"
    write_json(json_path, {"clips": clips})
    markdown_lines = ["# Short Video Publish Copy", ""]
    for clip in clips:
        markdown_lines.extend(
            [
                f"## {clip['sequence']:03d}. {clip['headline']}",
                "",
                f"- Clip: {clip['clip_file']}",
                f"- Hook: {clip['short_hook']}",
                f"- Description: {clip['description']}",
                f"- CTA: {clip['cta']}",
                f"- Hashtags: {' '.join(clip['hashtags'])}",
                "",
            ]
        )
    write_text(md_path, "\n".join(markdown_lines).rstrip() + "\n")
    return {"json": json_path, "md": md_path}


def write_operations_manual(ops_dir: Path, clips: list[dict[str, Any]]) -> Path:
    manual_path = ops_dir / "operations_manual.md"
    lines = [
        "# Short Video Operations Manual",
        "",
        "这是一份统一运营手册，汇总所有切片的发布介绍、推荐文案、平台建议、风险提示与发布前检查项。",
        "",
        "## 使用说明",
        "",
        "1. 先通读每个切片的发布介绍，确认主打信息与目标平台。",
        "2. 发布前核对标题、描述、标签与口播上下文是否一致。",
        "3. 如涉及争议表达、绝对化结论或嘉宾观点，请人工复核后再发布。",
        "",
    ]
    for clip in clips:
        lines.extend(
            [
                f"## {clip['sequence']:03d}. {clip['headline']}",
                "",
                "### 发布介绍",
                clip["description"],
                "",
                "### 发布素材",
                f"- 视频文件：{clip['clip_file']}",
                f"- 开场钩子：{clip['short_hook']}",
                f"- 行动引导：{clip['cta']}",
                f"- 话题标签：{' '.join(clip['hashtags'])}",
                "",
                "### 平台发布建议",
                "- 抖音/视频号：优先使用短标题和强开头，首屏尽快抛出核心观点。",
                "- 小红书：描述可补充问题背景，强调观点价值与适用人群。",
                "- B站/公众号导流：可结合来源内容补充上下文，降低断章取义风险。",
                "",
                "### 推荐发布文案",
                clip["description"],
                "",
                "### 风险提示",
                "- 标题与描述不要夸大结论，避免把单一观点包装成普遍事实。",
                "- 发布前确认片段没有脱离上下文，避免因截取过短导致误解。",
                "- 如涉及人物评价、行业判断或可争议表述，需人工复核措辞。",
                "",
                "### 发布前检查",
                "- [ ] 标题与视频内容一致",
                "- [ ] 口播重点与封面文案一致",
                "- [ ] 标签、CTA、平台描述已按目标渠道调整",
                "- [ ] 无明显断章取义、事实错误或容易引战的表述",
                "",
            ]
        )
    write_text(manual_path, "\n".join(lines).rstrip() + "\n")
    return manual_path


def write_full_article_assets(ops_dir: Path, article: dict[str, Any]) -> dict[str, Path]:
    json_path = ops_dir / "full_article.json"
    md_path = ops_dir / "full_article.md"
    docx_path = ops_dir / "full_article.docx"
    pdf_path = ops_dir / "full_article.pdf"

    write_json(json_path, {key: value for key, value in article.items() if key != "markdown"})
    write_text(md_path, article["markdown"] + "\n")
    _write_docx_from_markdown(md_path, docx_path)
    _write_pdf_from_markdown(md_path, pdf_path)
    return {
        "json": json_path,
        "md": md_path,
        "docx": docx_path,
        "pdf": pdf_path,
    }


def write_publish_manifest(
    ops_dir: Path,
    clips: list[dict[str, Any]],
    article_assets: dict[str, Path] | None = None,
    operations_manual_path: Path | None = None,
) -> Path:
    payload: dict[str, Any] = {"clips": clips}
    if article_assets:
        payload["full_article"] = {key: str(path) for key, path in article_assets.items()}
    if operations_manual_path:
        payload["operations_manual"] = str(operations_manual_path)
    manifest_path = ops_dir / "publish_manifest.json"
    summary_path = ops_dir / "package_summary.md"
    write_json(manifest_path, payload)
    summary_lines = ["# Publishing Package", ""]
    for clip in clips:
        summary_lines.append(f"- {clip['sequence']:03d} {clip['headline']}")
    if operations_manual_path:
        summary_lines.extend(
            [
                "",
                "## Operations Manual",
                f"- Markdown: {operations_manual_path.name}",
            ]
        )
    if article_assets:
        summary_lines.extend(
            [
                "",
                "## Full Interview Package",
                f"- Markdown: {article_assets['md'].name}",
                f"- Word: {article_assets['docx'].name}",
                f"- PDF: {article_assets['pdf'].name}",
            ]
        )
    write_text(summary_path, "\n".join(summary_lines) + "\n")
    return manifest_path


def _normalize_utterances(
    utterances: list[dict[str, Any]],
    *,
    host_name: str | None,
    guest_name: str | None,
) -> list[dict[str, Any]]:
    host_aliases = {value for value in [host_name, "主持人", "主播", "host"] if value}
    guest_aliases = {value for value in [guest_name, "嘉宾", "guest"] if value}
    normalized: list[dict[str, Any]] = []
    for utterance in utterances:
        raw_speaker = str(utterance.get("speaker") or "").strip()
        speaker = raw_speaker
        if raw_speaker in host_aliases and host_name:
            speaker = host_name
        elif raw_speaker in guest_aliases and guest_name:
            speaker = guest_name
        elif raw_speaker.startswith("SPEAKER_"):
            speaker = host_name if not normalized and host_name else guest_name or raw_speaker
        normalized.append(
            {
                "speaker": speaker or "未知讲者",
                "text": _clean_text(str(utterance.get("text", ""))),
            }
        )
    return [item for item in normalized if item["text"]]


def _build_sections(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged_turns: list[dict[str, Any]] = []
    for utterance in utterances:
        if merged_turns and merged_turns[-1]["speaker"] == utterance["speaker"]:
            merged_turns[-1]["text"] = f"{merged_turns[-1]['text']} {utterance['text']}".strip()
        else:
            merged_turns.append(dict(utterance))

    sections: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    for turn in merged_turns:
        speaker = turn["speaker"]
        text = turn["text"]
        if current_section is None:
            current_section = _new_section(_make_section_title(text, len(sections) + 1), speaker, text)
            continue

        if _is_question_like(text):
            if current_section["question_speaker"] == speaker and not current_section["answers"]:
                current_section["question"] = f"{current_section['question']} {text}".strip()
            elif current_section["answers"]:
                sections.append(current_section)
                current_section = _new_section(_make_section_title(text, len(sections) + 1), speaker, text)
            else:
                current_section["question"] = f"{current_section['question']} {text}".strip()
                current_section["question_speaker"] = speaker
            continue

        if current_section["answers"] and current_section["answers"][-1]["speaker"] == speaker:
            current_section["answers"][-1]["text"] = f"{current_section['answers'][-1]['text']} {text}".strip()
        else:
            current_section["answers"].append({"speaker": speaker, "text": text})

    if current_section:
        sections.append(current_section)
    return sections


def _new_section(title: str, speaker: str, question: str) -> dict[str, Any]:
    return {
        "title": title,
        "question_speaker": speaker,
        "question": question,
        "answers": [],
    }


def _make_section_title(text: str, index: int) -> str:
    cleaned = re.sub(r"[？?。！!]+$", "", text).strip()
    snippet = cleaned[:18].strip() or f"主题{index}"
    return f"0{index}. {snippet}" if index < 10 else f"{index}. {snippet}"


def _is_question_like(text: str) -> bool:
    question_mark = text.endswith(("？", "?"))
    starter = text.startswith(("所以", "那", "如果", "为什么", "怎么", "能不能", "是否", "你刚才", "你提到"))
    return question_mark or starter


def _build_cover_title(title: str, sections: list[dict[str, Any]]) -> str:
    if sections:
        lead = sections[0]["title"].split(". ", 1)[-1]
        return f"{lead}讲透了：{title}里最值得反复看的内容"
    return f"一次看懂《{title}》完整版访谈精华"


def _build_article_summary(sections: list[dict[str, Any]]) -> str:
    topics = [section["title"].split(". ", 1)[-1] for section in sections[:4]]
    if not topics:
        return "本篇整理了完整访谈的核心内容。"
    return "这篇完整版访谈主要讲了" + "、".join(topics) + "。"


def _render_article_markdown(
    *,
    cover_title: str,
    original_title: str,
    host_name: str | None,
    guest_name: str | None,
    sections: list[dict[str, Any]],
    transcript_text: str,
    template_id: str,
) -> str:
    lines = [f"# {cover_title}", "", f"{EDITOR_CREDIT}", ""]
    if host_name or guest_name:
        lines.append(f"主持人：{host_name or '待补充'}")
        lines.append(f"嘉宾：{guest_name or '待补充'}")
        lines.append("")
    lines.extend(
        [
            f"原始标题：{original_title}",
            f"内容类型：{template_id}",
            "",
            "## 导读",
            _build_article_summary(sections),
            "",
        ]
    )
    if not sections and transcript_text.strip():
        lines.extend(["## 完整内容", transcript_text.strip(), ""])
        return "\n".join(lines).strip()

    for section in sections:
        lines.append(f"## {section['title']}")
        lines.append("")
        lines.append(f"{section['question_speaker']}：{section['question']}")
        lines.append("")
        for answer in section["answers"]:
            lines.append(f"{answer['speaker']}：{answer['text']}")
            lines.append("")
    return "\n".join(lines).strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_headline_length(text: str, limit: int = 20) -> str:
    cleaned = re.sub(r"\s+", "", str(text)).strip()
    if len(cleaned) <= limit:
        return cleaned
    truncated = cleaned[:limit].rstrip("，。、！？：；|｜- ")
    return truncated or cleaned[:limit]


def _build_topic_lane(topic: str, limit: int = 10) -> str:
    cleaned = re.sub(r"[|｜]+", " ", str(topic)).strip()
    compact = re.sub(r"\s+", "", cleaned)
    if len(compact) <= limit:
        return compact or "AI话题"
    truncated = compact[:limit].rstrip("，。、！？：；|｜- ")
    return truncated or compact[:limit]


def _write_docx_from_markdown(markdown_path: Path, docx_path: Path) -> None:
    try:
        subprocess.run(
            ["pandoc", str(markdown_path), "-o", str(docx_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        _write_minimal_docx(markdown_path.read_text(encoding="utf-8"), docx_path)


def _write_pdf_from_markdown(markdown_path: Path, pdf_path: Path) -> None:
    commands = [
        ["pandoc", str(markdown_path), "-o", str(pdf_path), "--pdf-engine=weasyprint"],
        ["pandoc", str(markdown_path), "-o", str(pdf_path)],
    ]
    for command in commands:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            return
        except Exception:
            continue
    raise RuntimeError("failed to generate pdf from markdown")


def _write_minimal_docx(content: str, docx_path: Path) -> None:
    paragraphs = []
    for line in content.splitlines():
        text = line.strip()
        if not text:
            paragraphs.append("<w:p/>")
            continue
        paragraphs.append(
            "<w:p><w:r><w:t xml:space=\"preserve\">"
            + escape(text)
            + "</w:t></w:r></w:p>"
        )
    document_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" mc:Ignorable=\"w14 wp14\">"
        "<w:body>"
        + "".join(paragraphs)
        + "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"720\" w:footer=\"720\" w:gutter=\"0\"/></w:sectPr>"
        "</w:body></w:document>"
    )
    content_types_xml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/></Types>"
    rels_xml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/></Relationships>"
    docx_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(docx_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", rels_xml)
        archive.writestr("word/document.xml", document_xml)
