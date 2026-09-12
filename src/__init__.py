"""
SKILLOR — France-first YouTube Shorts Studio
=======================================

Automated YouTube Shorts / Facebook Reels pipeline that generates
vidéos de science du quotidien en français, de bout en bout:
  Script → Images → Voice → Video → SEO → Upload

Public API
----------
Main pipeline entry point::

    from src.main import SKILLORPipeline
    pipeline = SKILLORPipeline()
    pipeline.run_pipeline(topic="Pourquoi une paupière tressaille")

Individual modules (for testing / advanced use)::

    from src.script_generator import generate_script
    from src.image_providers import available_providers
    from src.voice_generator import generate_voice_segments
    from src.video_editor import build_video
    from src.uploader import upload_all
    from src.niche_strategy import get_random_topic
    from src.quality_checker import QualityChecker
    from src.scheduler import FrancePeakTimeScheduler
    from src.anti_spam import AntiSpamSystem
    from src.seo_generator import generate_seo_package
    from src.seo_analytics import predict_ctr, score_thumbnail
    from src.shorts_enhancer import build_shorts_report, generate_srt
    from src.media_validator import validate_scene_image, probe_video
"""

__version__ = "1.0.0"
__author__ = "jashaidaslamhfd"

# ---------------------------------------------------------------------------
# Lazy public API — importing `src` alone does NOT pull in heavy deps
# (torch, moviepy, groq, etc.). Consumers can still do `from src.X import Y`
# directly for granular access; these convenience re-exports are optional.
# ---------------------------------------------------------------------------

__all__ = [
    "AntiSpamSystem",
    "FrancePeakTimeScheduler",
    # Quality / Spam
    "QualityChecker",
    "RateLimitError",
    # Pipeline
    "SKILLORPipeline",
    # Image
    "available_providers",
    # Shorts
    "build_shorts_report",
    # Video
    "build_video",
    # Script
    "generate_script",
    "generate_seo_package",
    "generate_seo_tags",
    "generate_srt",
    "generate_thumbnail",
    "generate_voice",
    # Voice
    "generate_voice_segments",
    # Niche / SEO
    "get_random_topic",
    "get_topic_category",
    # Analytics
    "predict_ctr",
    "probe_video",
    "score_thumbnail",
    # Upload
    "upload_all",
    # Validation
    "validate_scene_image",
]

# ---------------------------------------------------------------------------
# Lazy public API. Previously __all__ was declared with NO imports and NO
# __getattr__, so every advertised name raised AttributeError on
# `from src import X`. This mapping keeps imports lazy (no heavy
# torch/moviepy cost on plain `import src`) while making the documented API
# actually resolvable.
# ---------------------------------------------------------------------------

_LAZY_EXPORTS = {
    "SKILLORPipeline": "src.main",
    "generate_script": "src.script_generator",
    "available_providers": "src.image_providers",
    "RateLimitError": "src.image_providers",
    "generate_voice_segments": "src.voice_generator",
    "generate_voice": "src.voice_generator",
    "build_video": "src.video_editor",
    "generate_thumbnail": "src.video_editor",
    "upload_all": "src.uploader",
    "get_random_topic": "src.niche_strategy",
    "get_topic_category": "src.niche_strategy",
    "generate_seo_tags": "src.niche_strategy",
    "generate_seo_package": "src.seo_generator",
    "QualityChecker": "src.quality_checker",
    "FrancePeakTimeScheduler": "src.scheduler",
    "AntiSpamSystem": "src.anti_spam",
    "predict_ctr": "src.seo_analytics",
    "score_thumbnail": "src.seo_analytics",
    "build_shorts_report": "src.shorts_enhancer",
    "generate_srt": "src.shorts_enhancer",
    "validate_scene_image": "src.media_validator",
    "probe_video": "src.media_validator",
}


def __getattr__(name):
    """Resolve public API names on first access (PEP 562)."""
    if name in _LAZY_EXPORTS:
        import importlib
        import os
        import sys

        # Modules inside src/ use flat sibling imports (`from seo_generator
        # import ...`), which only resolve with src/ itself on sys.path —
        # same trick src/main.py has always used.
        _src_dir = os.path.dirname(os.path.abspath(__file__))
        if _src_dir not in sys.path:
            sys.path.insert(0, _src_dir)
        module = importlib.import_module(_LAZY_EXPORTS[name])
        attr = getattr(module, name)
        globals()[name] = attr
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
