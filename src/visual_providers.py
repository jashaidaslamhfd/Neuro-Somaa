from __future__ import annotations

import os
import re
import hashlib
import subprocess
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageOps

from config import Settings


def _query(text: str) -> str:
    words = re.sub(r"[^\wÀ-ÿ -]", " ", text, flags=re.UNICODE).split()
    return quote(" ".join(words[:8]) or "science cerveau")


def _save_image(url: str, path: Path) -> Path | None:
    try:
        response = requests.get(url, timeout=18, headers={"User-Agent": "Neuro-Somaa/1.0"})
        response.raise_for_status()
        path.write_bytes(response.content)
        with Image.open(path) as image:
            image = ImageOps.fit(image.convert("RGB"), (1080, 1920), method=Image.Resampling.LANCZOS)
            image.save(path, format="JPEG", quality=88, optimize=True)
        return path
    except (OSError, requests.RequestException):
        path.unlink(missing_ok=True)
        return None


def _save_video(url: str, path: Path) -> Path | None:
    """Download a provider clip; ffmpeg normalizes it during rendering."""
    try:
        response = requests.get(url, timeout=30, headers={"User-Agent": "Neuro-Somaa/1.0"}, stream=True)
        response.raise_for_status()
        with path.open("wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if chunk:
                    output.write(chunk)
        if path.stat().st_size < 10_000:
            raise OSError("video response was unexpectedly small")
        return path
    except (OSError, requests.RequestException):
        path.unlink(missing_ok=True)
        return None


def _pexels(caption: str, path: Path) -> Path | None:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return None
    try:
        response = requests.get("https://api.pexels.com/v1/search", params={"query": caption, "orientation": "portrait", "per_page": 1}, headers={"Authorization": key}, timeout=18)
        response.raise_for_status()
        photos = response.json().get("photos", [])
        return _save_image(photos[0]["src"]["portrait"], path) if photos else None
    except (KeyError, ValueError, requests.RequestException):
        return None


def _pexels_clip(caption: str, path: Path) -> Path | None:
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return None
    try:
        response = requests.get("https://api.pexels.com/videos/search", params={"query": caption, "orientation": "portrait", "size": "medium", "per_page": 20}, headers={"Authorization": key}, timeout=18)
        response.raise_for_status()
        videos = response.json().get("videos", [])
        offset = int(hashlib.sha256(caption.encode()).hexdigest()[:8], 16) % max(1, len(videos))
        for video in videos[offset:] + videos[:offset]:
            files = sorted(video.get("video_files", []), key=lambda item: item.get("width", 0), reverse=True)
            portrait = [item for item in files if item.get("height", 0) > item.get("width", 0)]
            selected = (portrait or files)[0] if (portrait or files) else None
            if selected and selected.get("link"):
                return _save_video(selected["link"], path)
    except (KeyError, ValueError, requests.RequestException):
        return None
    return None


def _pixabay(caption: str, path: Path) -> Path | None:
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return None
    try:
        response = requests.get("https://pixabay.com/api/", params={"key": key, "q": caption, "orientation": "vertical", "image_type": "photo", "per_page": 3, "safesearch": "true"}, timeout=18)
        response.raise_for_status()
        hits = response.json().get("hits", [])
        return _save_image(hits[0]["largeImageURL"], path) if hits else None
    except (KeyError, ValueError, requests.RequestException):
        return None


def _pixabay_clip(caption: str, path: Path) -> Path | None:
    key = os.getenv("PIXABAY_API_KEY")
    if not key:
        return None
    try:
        response = requests.get("https://pixabay.com/api/videos/", params={"key": key, "q": caption, "orientation": "vertical", "per_page": 5, "safesearch": "true"}, timeout=18)
        response.raise_for_status()
        hits = response.json().get("hits", [])
        offset = int(hashlib.sha256(caption.encode()).hexdigest()[:8], 16) % max(1, len(hits))
        for hit in hits[offset:] + hits[:offset]:
            files = hit.get("videos", {})
            selected = files.get("medium") or files.get("small") or files.get("tiny")
            if selected and selected.get("url"):
                return _save_video(selected["url"], path)
    except (KeyError, ValueError, requests.RequestException):
        return None
    return None


def _coverr_clip(caption: str, path: Path) -> Path | None:
    """Fetch a Coverr clip; Coverr returns signed URLs when urls=true."""
    key = os.getenv("COVERR_API_KEY")
    if not key:
        return None
    try:
        response = requests.get(
            "https://api.coverr.co/videos",
            params={"api_key": key, "query": caption, "page_size": 20, "urls": "true", "sort": "popular"},
            timeout=18,
        )
        response.raise_for_status()
        hits = response.json().get("hits", [])
        offset = int(hashlib.sha256(caption.encode()).hexdigest()[:8], 16) % max(1, len(hits))
        for video in hits[offset:] + hits[:offset]:
            if not video.get("is_vertical"):
                continue
            url = (video.get("urls") or {}).get("mp4_download") or (video.get("urls") or {}).get("mp4")
            if url:
                return _save_video(url, path)
    except (KeyError, ValueError, requests.RequestException):
        return None
    return None


def _commons_clip(caption: str, path: Path) -> Path | None:
    try:
        response = requests.get("https://commons.wikimedia.org/w/api.php", params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": f"{caption} filetype:video", "gsrnamespace": 6,
            "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|mime",
        }, headers={"User-Agent": "Neuro-Somaa/1.0"}, timeout=25)
        response.raise_for_status()
        candidates = [p.get("imageinfo", [{}])[0].get("url") for p in response.json().get("query", {}).get("pages", {}).values()
                      if p.get("imageinfo") and p["imageinfo"][0].get("mime", "").startswith("video/")]
        if not candidates:
            return None
        return _save_video(candidates[int(os.getenv("GITHUB_RUN_ID", "0")) % len(candidates)], path)
    except (KeyError, ValueError, requests.RequestException):
        return None


def _archive_clip(caption: str, path: Path) -> Path | None:
    try:
        search = requests.get("https://archive.org/advancedsearch.php", params={
            "q": f"mediatype:movies AND collection:opensource_movies AND ({caption})",
            "fl[]": "identifier", "rows": 20, "output": "json",
        }, headers={"User-Agent": "Neuro-Somaa/1.0"}, timeout=25)
        search.raise_for_status()
        candidates = []
        for doc in search.json().get("response", {}).get("docs", []):
            meta = requests.get(f"https://archive.org/metadata/{doc['identifier']}", timeout=25)
            if not meta.ok:
                continue
            for item in meta.json().get("files", []):
                name = item.get("name", "")
                if name.lower().endswith((".mp4", ".webm", ".ogv")) and int(item.get("size", 0) or 0) < 200_000_000:
                    candidates.append(f"https://archive.org/download/{doc['identifier']}/{quote(name)}")
                    break
        if not candidates:
            return None
        return _save_video(candidates[int(os.getenv("GITHUB_RUN_ID", "0")) % len(candidates)], path)
    except (KeyError, ValueError, requests.RequestException):
        return None


def _pollinations(caption: str, path: Path) -> Path | None:
    # Optional AI visual provider. It is used only when explicitly configured.
    if not os.getenv("POLLINATIONS_KEY") and not os.getenv("GEMINI_API_KEY") and not os.getenv("REPLICATE_API_TOKEN"):
        return None
    prompt = quote(f"vertical editorial science illustration, French educational short, no text, clean modern lighting, concept: {caption}")
    return _save_image(f"https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1920&nologo=true", path)


def fetch_visual(caption: str, scene_index: int, output_dir: Path, settings: Settings) -> tuple[Path | None, str]:
    clip_path = output_dir / f"source_{scene_index:02d}.mp4"
    image_path = output_dir / f"source_{scene_index:02d}.jpg"
    # Search variations prevent every scene from selecting the same first-ranked
    # stock result when providers return deterministic ordering.
    variations = ("wide shot", "close up", "slow motion", "hands", "silhouette", "macro", "night", "abstract")
    run_salt = os.getenv("GITHUB_RUN_ID", "local")
    variation_index = int(hashlib.sha256(f"{run_salt}:{caption}:{scene_index}".encode()).hexdigest()[:8], 16) % len(variations)
    search_caption = f"{caption} {variations[variation_index]} documentary footage"
    # Prefer real moving footage. Image providers remain the safe fallback.
    for provider in (_pexels_clip, _pixabay_clip, _coverr_clip, _commons_clip, _archive_clip):
        visual = provider(search_caption, clip_path)
        if visual:
            return visual, provider.__name__.lstrip("_")
    return None, "no_moving_clip"
