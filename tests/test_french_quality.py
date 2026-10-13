from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from content import _fallback_script, score_hook, score_script_quality
from french_quality import validate_french_script
from growth import apply_growth_metadata, is_weak_title


def test_final_gate_rejects_off_niche_title_leakage():
    script = _fallback_script("Pourquoi le cerveau invente-t-il de faux souvenirs ?")
    bad_titles = [
        "Pourquoi on lui découvre deux tumeurs?",
        "Pourquoi quatre artistes explorent la?",
        "Pourquoi jour de mémoire et de leçons?",
        "Pourquoi le cancer au cerveau?",
    ]
    for title in bad_titles:
        script["title"] = title
        errors = validate_french_script(script, 18, 30)
        assert any("article-shaped ou hors ligne éditoriale" in error for error in errors), title


def test_final_gate_allows_reusable_brain_curiosity_title():
    script = _fallback_script("Pourquoi le cerveau invente-t-il de faux souvenirs ?")
    script["title"] = "Pourquoi le cerveau invente-t-il de faux souvenirs ?"
    errors = validate_french_script(script, 18, 30)
    assert not any("titre" in error for error in errors)


def test_deterministic_fallback_passes_the_same_production_gates():
    topic = "Pourquoi le stress déforme"
    script = _fallback_script(topic)
    script["topic"] = topic
    script = apply_growth_metadata(script)

    errors = validate_french_script(script, 18, 30)
    assert not errors, errors
    assert not is_weak_title(script["title"])
    assert score_hook(script["title"], script["scenes"][0]["caption"]) >= 70
    assert score_script_quality(script["scenes"]) >= 60
    assert 42 <= sum(len(scene["narration"].split()) for scene in script["scenes"]) <= 72


def test_growth_title_shaper_does_not_insert_duplicate_french_article():
    topic = "Pourquoi le stress déforme"
    script = _fallback_script(topic)
    script["topic"] = topic
    shaped = apply_growth_metadata(script)["title"]

    assert "ton le " not in shaped.lower()
    assert not is_weak_title(shaped)
