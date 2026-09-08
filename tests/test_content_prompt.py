from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from config import Settings
from content import FALLBACK_TOPICS, MYSTERY_STRUCTURE_GUIDE, generate_script


def _mock_groq(payloads: list[dict]):
    call_count = {"n": 0}

    def fake_create(*args, **kwargs):
        # First call is the system+user prompt — assert the structure guide
        # actually made it into what the model sees.
        if call_count["n"] == 0:
            system_content = kwargs["messages"][0]["content"]
            assert "STRUCTURE NARRATIVE" in system_content
            assert "REBONDISSEMENT" in system_content
            assert "RÉVÉLATION" in system_content
        payload = payloads[min(call_count["n"], len(payloads) - 1)]
        call_count["n"] += 1
        message = MagicMock()
        message.message.content = json.dumps(payload)
        response = MagicMock()
        response.choices = [message]
        return response

    client = MagicMock()
    client.chat.completions.create.side_effect = fake_create
    return client, call_count


def test_mystery_structure_guide_is_sent_to_the_llm(monkeypatch):
    strong = {
        "title": "Pourquoi ton cerveau oublie-t-il tes rêves ?",
        "description": "desc",
        "scenes": [{"caption": c, "narration": c} for c in [
            "ATTENDS—ton cerveau efface ça.", "La mémoire trie vite.", "Le rêve part en secondes.",
            "Ton cerveau garde l'essentiel.", "Mais un détail change tout.", "Le reste est effacé.",
            "C'est un tri normal.", "Observe-le ce soir.",
        ]],
    }
    client, call_count = _mock_groq([strong])
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    with patch("groq.Groq", return_value=client):
        settings = Settings()
        settings.dry_run = False
        result = generate_script("Pourquoi on oublie ses rêves", settings)
    assert call_count["n"] == 1
    assert result["title"] not in FALLBACK_TOPICS


def test_structure_guide_defines_all_eight_roles():
    roles = ("ACCROCHE", "MYSTÈRE", "INDICE 1", "INDICE 2", "REBONDISSEMENT", "INDICE 3", "RÉVÉLATION", "LA CHUTE")
    for role in roles:
        assert role in MYSTERY_STRUCTURE_GUIDE
