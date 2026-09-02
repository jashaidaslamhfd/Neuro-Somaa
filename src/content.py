from __future__ import annotations

import json
import os
import re
from typing import Any

from config import Settings

FALLBACK_TOPICS = [
    "Pourquoi votre cerveau bâille-t-il quand quelqu’un bâille ?",
    "Pourquoi la peau se couvre-t-elle de chair de poule ?",
    "Pourquoi un souvenir revient-il avec une odeur ?",
    "Pourquoi le cœur accélère-t-il avant une décision ?",
    "Pourquoi les jambes tremblent-elles sous le stress ?",
]


def load_topic(settings: Settings) -> str:
    if settings.topic:
        return settings.topic
    queue = settings.data_dir / "search_demand_queue_fr.json"
    if queue.exists():
        try:
            payload = json.loads(queue.read_text(encoding="utf-8"))
            items = payload if isinstance(payload, list) else payload.get("topics", [])
            for item in items:
                title = item.get("title") if isinstance(item, dict) else str(item)
                if title:
                    return str(title)
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    history = settings.data_dir / "video_history.json"
    used = set()
    if history.exists():
        try:
            rows = json.loads(history.read_text(encoding="utf-8"))
            used = {str(row.get("topic", "")).lower() for row in rows if isinstance(row, dict)}
        except (OSError, json.JSONDecodeError):
            pass
    return next((topic for topic in FALLBACK_TOPICS if topic.lower() not in used), FALLBACK_TOPICS[0])


def _fallback_script(topic: str) -> dict[str, Any]:
    clean = topic.strip().rstrip("?")
    return {
        "title": clean + " ?",
        "description": f"Une explication claire et courte sur {clean.lower()}. #shorts #science",
        "tags": ["science", "cerveau", "corps humain", "curiosité", "shorts"],
        "scenes": [
            {"caption": clean + " ?", "narration": clean + " ?"},
            {"caption": "La réponse commence dans votre cerveau.", "narration": "La réponse commence dans votre cerveau."},
            {"caption": "Il détecte un signal avant même votre conscience.", "narration": "Il détecte un signal avant même votre conscience."},
            {"caption": "Puis votre corps prépare une réaction rapide.", "narration": "Puis votre corps prépare une réaction rapide."},
            {"caption": "Ce mécanisme est ancien, mais toujours utile.", "narration": "Ce mécanisme est ancien, mais toujours utile."},
            {"caption": "Observez-le la prochaine fois que cela arrive.", "narration": "Observez-le la prochaine fois que cela arrive."},
        ],
    }


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM returned no JSON object")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict) or not payload.get("scenes"):
        raise ValueError("LLM JSON has no scenes")
    return payload


def generate_script(topic: str, settings: Settings) -> dict[str, Any]:
    if settings.dry_run or not settings.llm_keys:
        return _fallback_script(topic)
    api_key = os.getenv(settings.llm_keys[0], "")
    if settings.llm_keys[0] == "GROQ_API_KEY":
        try:
            from groq import Groq
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=settings.llm_model,
                temperature=0.6,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Tu écris des Shorts scientifiques en français naturel. Réponds uniquement en JSON."},
                    {"role": "user", "content": (
                        f"Sujet: {topic}\nCrée un titre de moins de 70 caractères et 6 scènes. "
                        f"Chaque scène doit contenir caption et narration en français. Durée cible {settings.min_seconds:g}-{settings.max_seconds:g}s."
                    )},
                ],
            )
            return _extract_json(response.choices[0].message.content or "")
        except Exception:
            return _fallback_script(topic)
    return _fallback_script(topic)
