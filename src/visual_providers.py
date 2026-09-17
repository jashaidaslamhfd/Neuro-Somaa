from __future__ import annotations

import hashlib
import os
import re
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
        return _save_video(candidates[int(hashlib.sha256(f"{os.getenv('GITHUB_RUN_ID', '0')}:{caption}".encode()).hexdigest()[:8], 16) % len(candidates)], path)
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
        return _save_video(candidates[int(hashlib.sha256(f"{os.getenv('GITHUB_RUN_ID', '0')}:{caption}".encode()).hexdigest()[:8], 16) % len(candidates)], path)
    except (KeyError, ValueError, requests.RequestException):
        return None


def _pollinations(caption: str, path: Path) -> Path | None:
    # Optional AI visual provider. It is used only when explicitly configured.
    if not os.getenv("POLLINATIONS_KEY") and not os.getenv("GEMINI_API_KEY") and not os.getenv("REPLICATE_API_TOKEN"):
        return None
    prompt = quote(f"vertical editorial science illustration, French educational short, no text, clean modern lighting, concept: {caption}")
    return _save_image(f"https://image.pollinations.ai/prompt/{prompt}?width=1080&height=1920&nologo=true", path)


_FR_SCIENCE_MAP = {
    "cerveau": "human brain neural",
    "sommeil": "person sleeping night",
    "rêve": "surreal dream clouds",
    "rêves": "surreal dream clouds",
    "stress": "stress anxiety overwhelmed",
    "cœur": "heartbeat human heart",
    "coeur": "heartbeat human heart",
    "bâill": "person yawning tired",
    "muscle": "human muscles anatomy",
    "nerveux": "nervous system neurons",
    "yeux": "human eye pupil close up",
    "œil": "human eye pupil close up",
    "oeil": "human eye pupil close up",
    "mémoire": "memory thoughts thinking",
    "peur": "fear suspense shadow",
    "corps": "human body biology",
    "fatigue": "tired person exhausted",
    "respiration": "breathing lungs air",
    "odeur": "smell aroma fragrance",
    "estomac": "human abdomen anatomy",
    "intestin": "human biology internal organs",
}


def _procedural_motion_clip(scene_index: int, path: Path, caption: str = "") -> Path:
    import time

    from PIL import ImageDraw

    palettes = (
        ("#101827", "#29476b", "#6ee7d8"),
        ("#180f2e", "#55318a", "#f5a3ff"),
        ("#102b2d", "#176b73", "#f7d774"),
        ("#2a1420", "#74324c", "#ffb36b"),
    )
    first, second, accent = palettes[(scene_index - 1) % len(palettes)]
    temp_img = path.with_suffix(f".tmp_{scene_index}.png")
    img = Image.new("RGB", (1080, 1920), first)
    draw = ImageDraw.Draw(img)

    # Dynamic entropy injection: ensures clip hash is distinct across runs.
    run_salt = os.getenv("GITHUB_RUN_ID", str(time.time()))
    entropy = int(hashlib.sha256(f"{run_salt}:{caption}:{scene_index}".encode()).hexdigest()[:8], 16)
    center_y = 960 + (entropy % 180) - 90
    center_x = 540 + ((entropy >> 8) % 120) - 60
    semantic = caption.lower()
    # The fallback remains deterministic, but its focal motif follows the
    # scene meaning instead of showing the same concentric rings every time.
    if any(word in semantic for word in ("cerveau", "mémoire", "neurone", "rêve")):
        draw.ellipse((center_x - 250, center_y - 190, center_x + 20, center_y + 190), outline=accent, width=18)
        draw.ellipse((center_x - 20, center_y - 190, center_x + 250, center_y + 190), outline=accent, width=18)
        for offset in (-120, -40, 40, 120):
            draw.line((center_x - 260, center_y + offset, center_x + 260, center_y - offset), fill=accent, width=7)
    elif any(word in semantic for word in ("téléphone", "écran", "ia", "robot", "algorithme")):
        draw.rounded_rectangle((center_x - 180, center_y - 330, center_x + 180, center_y + 330), radius=42, outline=accent, width=18)
        draw.line((center_x - 100, center_y - 220, center_x + 100, center_y - 220), fill=accent, width=10)
        draw.ellipse((center_x - 18, center_y + 250, center_x + 18, center_y + 286), fill=accent)
    elif any(word in semantic for word in ("œil", "oeil", "yeux", "regard")):
        draw.ellipse((center_x - 300, center_y - 150, center_x + 300, center_y + 150), outline=accent, width=18)
        draw.ellipse((center_x - 75, center_y - 75, center_x + 75, center_y + 75), fill=accent)
    else:
        for diagonal in range(-900, 1200, 180):
            draw.line((0, center_y + diagonal, 1080, center_y + diagonal - 500), fill=accent, width=8)
    draw.rounded_rectangle((70, 80, 1010, 215), radius=38, fill=second)
    draw.text((105, 112), "NEURO-SOMAA · SCIENCE DU QUOTIDIEN", fill="#ffffff")
    draw.text((88, 250), f"{scene_index:02d}", fill=accent)
    img.save(temp_img, format="PNG")
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(temp_img),
        "-vf",
        "zoompan=z='min(zoom+0.0012,1.25)':d=90:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30",
        "-t",
        "8.0",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    temp_img.unlink(missing_ok=True)
    return path


def fetch_visual(caption: str, scene_index: int, output_dir: Path, settings: Settings, used_hashes: set[str] | None = None, narration: str = "") -> tuple[Path | None, str]:
    clip_path = output_dir / f"source_{scene_index:02d}.mp4"
    if not settings.dry_run:
        variations = ("wide shot", "close up", "slow motion", "hands", "silhouette", "macro", "night", "abstract", "cinematic", "laboratory")
        run_salt = os.getenv("GITHUB_RUN_ID", "local")
        variation_index = (int(hashlib.sha256(f"{run_salt}:{caption}:{scene_index}".encode()).hexdigest()[:8], 16) + scene_index) % len(variations)
        
        # Search against the spoken meaning as well as the short caption.
        # Caption-only queries caused unrelated footage when a caption was
        # intentionally abstract or just a hook.
        semantic_text = f"{caption}. {narration}".strip()
        caption_lower = semantic_text.lower()
        search_term = "human biology science"
        for kw, term in _FR_SCIENCE_MAP.items():
            if kw in caption_lower:
                search_term = term
                break

        search_caption = f"{search_term} {semantic_text[:120]} {variations[variation_index]} documentary footage"
        for provider in (_pexels_clip, _pixabay_clip, _coverr_clip, _commons_clip, _archive_clip):
            visual = provider(search_caption, clip_path)
            if visual:
                # If this clip was already used in an earlier scene, fall through to procedural motion
                clip_h = hashlib.sha256(visual.read_bytes()).hexdigest()
                if used_hashes and clip_h in used_hashes:
                    continue
                return visual, provider.__name__.lstrip("_")

        # If an AI visual provider is configured, prefer a scene-specific
        # editorial still over generic procedural rings. The renderer animates
        # this image with a slow zoom while preserving exact captions.
        ai_visual = _pollinations(semantic_text, output_dir / f"scene_{scene_index:02d}_ai.jpg")
        if ai_visual:
            return ai_visual, "ai_editorial"

    motion_clip = _procedural_motion_clip(scene_index, clip_path, caption=f"{caption}:{scene_index}")
    return motion_clip, "procedural_motion"
