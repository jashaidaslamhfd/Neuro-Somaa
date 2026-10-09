from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from fetch_france_trends import is_good_topic


def test_rejects_historical_news_pollution_examples():
    assert not is_good_topic("Pourquoi quatre artistes explorent la mémoire à Concarneau ?")
    assert not is_good_topic("On lui découvre deux tumeurs au cerveau après une chute")
    assert not is_good_topic("Pourquoi jour de mémoire et de leçons politiques ?")
    assert not is_good_topic("Stress, surcharge mentale, perte de sens")


def test_keeps_evergreen_brain_curiosity_topics():
    assert is_good_topic("Pourquoi le cerveau invente-t-il de faux souvenirs ?")
    assert is_good_topic("Pourquoi une chanson reste-t-elle dans ta tête ?")
