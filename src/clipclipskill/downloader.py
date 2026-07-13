from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .workspace import ensure_dir, sha256_file, write_json

SUPPORTED_HOSTS = {
    "youtube": {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"},
    "bilibili": {"bilibili.com", "www.bilibili.com", "m.bilibili.com", "b23.tv"},
}


def _normalize_host(host: str) -> str:
    return host.lower().strip().removeprefix("www.")


def _detect_platform(host: str) -> str | None:
    normalized = _normalize_host(host)
    for platform, hosts in SUPPORTED_HOSTS.items():
        normalized_hosts = {_normalize_host(item) for item in hosts}
        if normalized in normalized_hosts:
            return platform
    return None


def validate_supported_url(raw_url: str) -> tuple[str, str]:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("url must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("url host is missing")
    platform = _detect_platform(parsed.netloc)
    if platform is None:
        raise ValueError("only YouTube and Bilibili URLs are supported")
    return parsed.geturl(), platform


def _pick_downloaded_file(source_dir: Path, info: dict) -> Path:
    requested = info.get("requested_downloads") or []
    for item in requested:
        filepath = item.get("filepath") or item.get("filename")
        if filepath:
            candidate = Path(filepath)
            if candidate.exists():
                return candidate
    filepath = info.get("_filename")
    if filepath:
        candidate = Path(filepath)
        if candidate.exists():
            return candidate
    matches = sorted(path for path in source_dir.iterdir() if path.is_file() and path.suffix != ".json")
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise RuntimeError("download succeeded but no media file was created")
    raise RuntimeError("download created multiple files and output file could not be determined")


def download_video_source(url: str, source_dir: Path) -> dict[str, str | dict]:
    try:
        from yt_dlp import YoutubeDL
    except ImportError as exc:
        raise RuntimeError("yt-dlp is not installed") from exc

    normalized_url, platform = validate_supported_url(url)
    ensure_dir(source_dir)
    metadata_path = source_dir / "download.json"
    output_template = str(source_dir / "source.%(ext)s")
    options = {
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "merge_output_format": "mp4",
        "restrictfilenames": True,
    }

    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(normalized_url, download=True)
        resolved_url = info.get("webpage_url") or info.get("original_url") or normalized_url

    media_path = _pick_downloaded_file(source_dir, info)
    payload = {
        "platform": platform,
        "origin_url": normalized_url,
        "resolved_url": resolved_url,
        "title": info.get("title"),
        "extractor": info.get("extractor"),
        "uploader": info.get("uploader"),
        "duration": info.get("duration"),
        "local_video_path": str(media_path),
        "source_sha256": sha256_file(media_path),
        "downloader": "yt-dlp",
        "raw": info,
    }
    write_json(metadata_path, payload)
    payload["download_metadata_path"] = str(metadata_path)
    return payload
