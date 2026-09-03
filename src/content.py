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

FRANCE_COPY_RULES = (
    "Écris en français de France métropolitaine, naturel et actuel. Utilise le tutoiement "
    "(tu, ton, ta, tes) pour parler directement au spectateur. Évite les calques de l’anglais, "
    "les tournures québécoises ou belges non nécessaires, le jargon administratif et les formulations "
    "trop littérales. Préfère des phrases courtes, fluides et orales, sans exagération médicale."
)


def _clean_fr(text: str) -> str:
    text = re.sub(r"\s+([?!:;…])", r"\1", text.strip())
    text = re.sub(r"\s{2,}", " ", text)
    return text


def load_topic(settings: Settings) -> str:
    if settings.topic:
        return _clean_fr(settings.topic)
    queue = settings.data_dir / "search_demand_queue_fr.json"
    if queue.exists():
        try:
            payload = json.loads(queue.read_text(encoding="utf-8"))
            items = payload if isinstance(payload, list) else payload.get("topics", [])
            for item in items:
                title = item.get("title") if isinstance(item, dict) else str(item)
                if title:
                    return _clean_fr(str(title))
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    history = settings.data_dir / "video_history.json"
    used = set()
    if history.exists():
        try:
            rows = json.loads(history.read_text(encoding="utf-8"))
            used = {_clean_fr(str(row.get("topic", ""))).lower() for row in rows if isinstance(row, dict)}
        except (OSError, json.JSONDecodeError):
            pass
    return next((topic for topic in FALLBACK_TOPICS if _clean_fr(topic).lower() not in used), FALLBACK_TOPICS[0])


def _fallback_script(topic: str) -> dict[str, Any]:
    clean = _clean_fr(topic).rstrip("?")
    return {
        "title": _clean_fr(clean + " ?"),
        "description": f"Tu vas comprendre pourquoi {clean.lower()}. Une explication claire en quelques secondes. #shorts #science",
        "tags": ["science", "cerveau", "corps humain", "curiosité", "shorts français"],
        "scenes": [
            {"caption": "ATTENDS—ton cerveau fait ça.", "narration": clean + " ?"},
            {"caption": "La réponse commence dans ton cerveau.", "narration": "La réponse commence dans ton cerveau."},
            {"caption": "Il repère d’abord un signal.", "narration": "Il repère d’abord un signal."},
            {"caption": "Puis il cherche un souvenir lié.", "narration": "Puis il cherche un souvenir lié."},
            {"caption": "Une odeur peut réveiller une émotion.", "narration": "Une odeur peut réveiller une émotion."},
            {"caption": "Le cerveau associe les deux très vite.", "narration": "Le cerveau associe les deux très vite."},
            {"caption": "C’est pourquoi le souvenir semble soudain.", "narration": "C’est pourquoi le souvenir semble soudain."},
            {"caption": "Observe-le la prochaine fois.", "narration": "Observe-le la prochaine fois."},
        ],
    }


def _extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM returned no JSON object")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict) or not payload.get("scenes"):
        raise ValueError("LLM JSON has no scenes")
    payload["title"] = _clean_fr(str(payload.get("title", "")))
    payload["description"] = _clean_fr(str(payload.get("description", "")))
    for scene in payload["scenes"]:
        scene["caption"] = _clean_fr(str(scene.get("caption", "")))
        scene["narration"] = _clean_fr(str(scene.get("narration", "")))
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
                    {"role": "system", "content": f"{FRANCE_COPY_RULES} Réponds uniquement en JSON valide."},
                    {"role": "user", "content": (
                        f"Sujet: {topic}\nCrée un titre de moins de 70 caractères et 8 scènes très courtes. "
                        "Chaque scène doit contenir caption et narration en français de France. "
                        f"Durée cible {settings.min_seconds:g}-{settings.max_seconds:g}s."
                    )},
                ],
            )
            result = _extract_json(response.choices[0].message.content or "")
            scenes = result.get("scenes", [])
            if (len(scenes) != 8 or not 3 <= len(str(scenes[0].get("caption", "")).split()) <= 7
                    or any(len(str(scene.get("caption", "")).split()) > 12 for scene in scenes)):
                raise ValueError("French script failed hook and caption-length gates")
            return result
        except Exception:
            return _fallback_script(topic)
    return _fallback_script(topic)
