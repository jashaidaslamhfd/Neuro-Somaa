from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from content import _fallback_script
from french_quality import validate_french_script


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
