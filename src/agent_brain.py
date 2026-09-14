"""Autonomous AI Agent Brain for Neuro-Somaa.
Implements the Sense -> Reason -> Act -> Learn loop:
1. Sense: Ingests YouTube Analytics & audience performance signals.
2. Memory: Maintains episodic knowledge of high-retention topics, hooks, and keywords.
3. Reason: Formulates video strategy, pacing, and mobile-first title constraints.
4. Act: Executes resilient generation, audio synthesis, and visual rendering.
5. Learn: Reflects on production metrics, updates channel memory, and self-optimizes.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017

logger = logging.getLogger("neuro_somaa.agent")

DEFAULT_MEMORY = {
    "version": "2.0.0",
    "agent_name": "Neuro-Somaa Autonomous Agent",
    "created_at": datetime.now(UTC).isoformat(),
    "last_cycle_at": None,
    "total_cycles": 0,
    "strategy": {
        "preferred_hook_style": "QUESTION_CURIOSITY",
        "target_duration_window": [16.0, 21.0],
        "max_title_chars": 42,
        "mobile_feed_optimized": True,
        "active_narrative_role": "POV_MYSTERY_INVESTIGATION"
    },
    "high_velocity_keywords": [
        {"keyword": "cerveau", "weight": 1.5, "engagement_avg": 8.8},
        {"keyword": "sommeil", "weight": 1.4, "engagement_avg": 8.5},
        {"keyword": "stress", "weight": 1.4, "engagement_avg": 8.2},
        {"keyword": "téléphone", "weight": 1.6, "engagement_avg": 9.1},
        {"keyword": "rêves", "weight": 1.3, "engagement_avg": 8.0},
        {"keyword": "mémoire", "weight": 1.3, "engagement_avg": 7.9}
    ],
    "winning_hooks": [
        "Ton téléphone vibre dans le vide ?",
        "Pourquoi oublie-t-on nos rêves ?",
        "Pourquoi le temps passe plus vite ?",
        "Pourquoi sursaute-t-on au lit ?"
    ],
    "performance_records": []
}


class AgentBrain:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or (Path(__file__).parents[1] / "data")
        self.memory_path = self.data_dir / "agent_memory.json"
        self.log_path = self.data_dir / "agent_log.json"
        self.memory = self._load_memory()

    def _load_memory(self) -> dict[str, Any]:
        if self.memory_path.exists():
            try:
                data = json.loads(self.memory_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Could not read agent memory (%s), initializing default.", exc)
        return json.loads(json.dumps(DEFAULT_MEMORY))

    def save_memory(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.memory["last_cycle_at"] = datetime.now(UTC).isoformat()
        self.memory_path.write_text(json.dumps(self.memory, ensure_ascii=False, indent=2), encoding="utf-8")

    def sense_youtube_performance(self) -> dict[str, Any]:
        """Sense phase: Connects to YouTube API to inspect channel analytics and recent video stats."""
        metrics: dict[str, Any] = {
            "channel_title": "Neuro-Somaa",
            "recent_videos_audited": 0,
            "top_performing_video": None,
            "sync_status": "offline_mode"
        }
        
        req_keys = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN")
        if not all(os.getenv(k) for k in req_keys):
            logger.info("YouTube OAuth credentials not available in environment; using local memory telemetry.")
            return metrics

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials(
                None,
                refresh_token=os.environ["REFRESH_TOKEN"],
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.environ["GOOGLE_CLIENT_ID"],
                client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
                scopes=["https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/youtube.force-ssl"]
            )
            creds.refresh(Request())
            yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

            # Get channel uploads playlist
            ch_resp = yt.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
            items = ch_resp.get("items", [])
            if items:
                ch = items[0]
                metrics["channel_title"] = ch["snippet"]["title"]
                metrics["total_views"] = int(ch["statistics"].get("viewCount", 0))
                metrics["subscribers"] = int(ch["statistics"].get("subscriberCount", 0))
                uploads_id = ch["contentDetails"]["relatedPlaylists"]["uploads"]

                # Fetch last 10 uploads
                p_resp = yt.playlistItems().list(part="contentDetails", playlistId=uploads_id, maxResults=10).execute()
                vid_ids = [it["contentDetails"]["videoId"] for it in p_resp.get("items", [])]
                if vid_ids:
                    v_resp = yt.videos().list(part="snippet,statistics", id=",".join(vid_ids)).execute()
                    audited = []
                    for v in v_resp.get("items", []):
                        stats = v.get("statistics", {})
                        audited.append({
                            "id": v["id"],
                            "title": v["snippet"]["title"],
                            "views": int(stats.get("viewCount", 0)),
                            "likes": int(stats.get("likeCount", 0)),
                            "comments": int(stats.get("commentCount", 0)),
                        })
                    metrics["recent_videos_audited"] = len(audited)
                    if audited:
                        best = max(audited, key=lambda x: x["views"])
                        metrics["top_performing_video"] = best
                        # If best video has high engagement, reinforce its keywords
                        self._reinforce_keywords_from_title(best["title"])
                    metrics["sync_status"] = "synced_live"
                    logger.info("Agent sensory loop successfully ingested %d live YouTube video metrics.", len(audited))
        except Exception as exc:
            logger.warning("Sensory YouTube feedback check encountered non-fatal issue: %s", exc)
            metrics["sync_status"] = f"warning: {exc}"

        return metrics

    def _reinforce_keywords_from_title(self, title: str) -> None:
        words = re.findall(r"\b[a-zà-ÿ]{4,}\b", title.lower())
        existing = {k["keyword"]: k for k in self.memory.get("high_velocity_keywords", [])}
        for w in words:
            if w in ("pourquoi", "dans", "avec", "pour", "cette", "votre"):
                continue
            if w in existing:
                existing[w]["weight"] = round(existing[w]["weight"] * 1.05, 2)
            else:
                self.memory.setdefault("high_velocity_keywords", []).append({
                    "keyword": w,
                    "weight": 1.2,
                    "engagement_avg": 8.0
                })

    def reason_and_strategize(self, chosen_topic: str) -> dict[str, Any]:
        """Reason phase: Formulates strategic parameters for generation."""
        # Calculate topic affinity with learned high-velocity keywords
        clean_topic = chosen_topic.lower()
        keyword_matches = [
            kw["keyword"] for kw in self.memory.get("high_velocity_keywords", [])
            if kw["keyword"] in clean_topic
        ]
        
        # Decide narrative tempo
        pacing = "ULTRA_DYNAMIC" if len(keyword_matches) >= 2 else "MYSTERY_BUILD"
        
        plan = {
            "cycle_timestamp": datetime.now(UTC).isoformat(),
            "target_topic": chosen_topic,
            "detected_keywords": keyword_matches,
            "chosen_tempo": pacing,
            "title_length_cap": self.memory.get("strategy", {}).get("max_title_chars", 42),
            "target_duration_window": self.memory.get("strategy", {}).get("target_duration_window", [15.0, 22.0]),
            "mobile_screen_constraint": "Strict single-line visibility in YouTube Shorts feed (no ellipsis)",
            "call_to_action": "High-retention comment provocation"
        }
        
        logger.info("Agent cognitive plan formulated: %s (Affinity: %s)", chosen_topic, keyword_matches or "novel")
        return plan

    def reflect_and_learn(self, production_result: dict[str, Any], plan: dict[str, Any]) -> None:
        """Learn phase: Stores outcome in memory, updates cognitive log."""
        self.memory["total_cycles"] = self.memory.get("total_cycles", 0) + 1
        
        record = {
            "cycle": self.memory["total_cycles"],
            "timestamp": datetime.now(UTC).isoformat(),
            "title": production_result.get("title"),
            "topic": production_result.get("topic"),
            "duration": production_result.get("duration"),
            "hook_score": production_result.get("hook_score"),
            "quality_score": production_result.get("quality_score"),
            "status": production_result.get("status"),
            "url": production_result.get("url"),
            "tempo": plan.get("chosen_tempo")
        }
        
        records = self.memory.setdefault("performance_records", [])
        records.append(record)
        self.memory["performance_records"] = records[-100:]  # Keep last 100
        
        if record.get("title") and len(record["title"]) <= 42:
            winning = self.memory.setdefault("winning_hooks", [])
            if record["title"] not in winning:
                winning.append(record["title"])
                self.memory["winning_hooks"] = winning[-30:]

        self.save_memory()

        # Append to agent log stream
        try:
            logs = []
            if self.log_path.exists():
                logs = json.loads(self.log_path.read_text(encoding="utf-8"))
                if not isinstance(logs, list):
                    logs = []
            logs.append({
                "cycle": self.memory["total_cycles"],
                "plan": plan,
                "outcome": record
            })
            self.log_path.write_text(json.dumps(logs[-150:], ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("Could not append to agent log: %s", exc)

        logger.info("Agent reflection complete. Cycle #%d recorded in memory.", self.memory["total_cycles"])
