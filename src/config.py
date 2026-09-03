from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


@dataclass
class Settings:
    language: str = field(default_factory=lambda: _env("CHANNEL_LANGUAGE", "fr"))
    timezone: str = field(default_factory=lambda: _env("PUBLISH_TIMEZONE", "Europe/Paris"))
    min_seconds: float = field(default_factory=lambda: float(_env("TARGET_MIN_SECONDS", "15")))
    max_seconds: float = field(default_factory=lambda: float(_env("TARGET_MAX_SECONDS", "30")))
    output_dir: Path = field(default_factory=lambda: Path(_env("OUTPUT_DIR", "output")))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "data")))
    privacy_status: str = field(default_factory=lambda: _env("YT_PRIVACY_STATUS", "private"))
    schedule_publish: bool = field(default_factory=lambda: _env("YT_SCHEDULE_PUBLISH", "true").lower() == "true")
    topic: str = field(default_factory=lambda: _env("VIDEO_TOPIC"))
    dry_run: bool = field(default_factory=lambda: _env("DRY_RUN", "false").lower() == "true")
    llm_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "llama-3.3-70b-versatile"))

    @property
    def llm_keys(self) -> tuple[str, ...]:
        return tuple(name for name in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "ALT_LLM_API_KEY") if _env(name))

    @property
    def visual_keys(self) -> tuple[str, ...]:
        return tuple(name for name in (
            "GEMINI_API_KEY", "REPLICATE_API_TOKEN", "HF_API_KEY", "PEXELS_API_KEY",
            "PIXABAY_API_KEY", "AI_HORDE_API_KEY", "DEEPAI_API_KEY", "MODELSLAB_API_KEY",
            "POLLINATIONS_KEY", "COVERR_API_KEY",
        ) if _env(name))

    @property
    def youtube_ready(self) -> bool:
        return all(_env(name) for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN"))

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.language != "fr":
            errors.append("CHANNEL_LANGUAGE must be fr for this French-first pipeline")
        if not 0 < self.min_seconds < self.max_seconds <= 60:
            errors.append("TARGET_MIN_SECONDS/TARGET_MAX_SECONDS must be a valid window within 60 seconds")
        if self.privacy_status not in {"private", "unlisted", "public"}:
            errors.append("YT_PRIVACY_STATUS must be private, unlisted, or public")
        if self.schedule_publish and self.privacy_status != "private":
            errors.append("Scheduled YouTube publishing requires YT_PRIVACY_STATUS=private")
        if not self.llm_keys and not self.dry_run:
            errors.append("At least one LLM secret is required outside dry-run mode")
        if not self.youtube_ready and not self.dry_run:
            errors.append("GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and REFRESH_TOKEN are required outside dry-run mode")
        return errors

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings()
