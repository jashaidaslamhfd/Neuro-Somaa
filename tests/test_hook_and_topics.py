from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from config import Settings
from content import _topic_retention_bonus, load_topic, score_hook, title_is_fresh


def test_near_duplicate_title_is_rejected(tmp_path):
    settings = Settings()
    settings.data_dir = tmp_path
    history = [{"title": "Pourquoi ton cerveau efface tes rêves la nuit ?"}]
    (tmp_path / "video_history.json").write_text(json.dumps(history), encoding="utf-8")
    assert title_is_fresh("Pourquoi ton cerveau efface tes rêves ?", settings) is False


def test_distinct_title_is_accepted(tmp_path):
    settings = Settings()
    settings.data_dir = tmp_path
    history = [{"title": "Pourquoi ton cerveau efface tes rêves la nuit ?"}]
    (tmp_path / "video_history.json").write_text(json.dumps(history), encoding="utf-8")
    assert title_is_fresh("Pourquoi tes muscles tremblent au froid ?", settings) is True


def test_shared_opening_word_alone_does_not_block(tmp_path):
    """Opener variety is a soft rubric nudge, not a hard gate — a channel
    whose whole history already opens with 'Pourquoi' must not fail every
    single future title for sharing that one word with no other overlap."""
    settings = Settings()
    settings.data_dir = tmp_path
    history = [{"title": f"Pourquoi sujet numéro {i} arrive ?"} for i in range(8)]
    (tmp_path / "video_history.json").write_text(json.dumps(history), encoding="utf-8")
    assert title_is_fresh("Pourquoi tes muscles tremblent-ils au froid ?", settings) is True


def test_question_style_hook_scores_well():
    score = score_hook("Pourquoi ton cerveau rêve-t-il ?", "ATTENDS—ton cerveau fait ça.")
    assert score >= 70


def test_statement_reveal_style_hook_scores_equally_well():
    score = score_hook("Ton cerveau efface tes rêves en secondes", "ATTENDS—ça arrive chaque nuit.")
    assert score >= 70


def test_flat_title_with_no_question_or_reveal_opener_is_penalized():
    score = score_hook("Le cerveau et les rêves", "Un fait sur le cerveau et les rêves.")
    assert score < 70


def test_load_topic_prefers_winning_cluster_within_lookahead_window(tmp_path):
    settings = Settings()
    settings.data_dir = tmp_path
    queue = [
        {"title": "Pourquoi ton cœur accélère-t-il ?"},
        {"title": "Pourquoi tes muscles tremblent-ils ?"},
        {"title": "Pourquoi tes yeux clignent-ils ?"},
    ]
    (tmp_path / "search_demand_queue_fr.json").write_text(json.dumps(queue), encoding="utf-8")
    (tmp_path / "video_history.json").write_text("[]", encoding="utf-8")
    topic = load_topic(settings)
    assert "muscle" in topic.lower()


def test_load_topic_falls_back_to_rotation_when_no_winning_topic_nearby(tmp_path):
    settings = Settings()
    settings.data_dir = tmp_path
    queue = [{"title": "Pourquoi ton cœur accélère-t-il ?"}, {"title": "Pourquoi tes yeux clignent-ils ?"}]
    (tmp_path / "search_demand_queue_fr.json").write_text(json.dumps(queue), encoding="utf-8")
    (tmp_path / "video_history.json").write_text("[]", encoding="utf-8")
    topic = load_topic(settings)
    assert "cœur" in topic.lower()


def test_topic_retention_bonus_uses_observed_analytics_not_predictions():
    history = [
        {"topic": "Pourquoi le sommeil aide la mémoire ?", "views": 120, "average_view_percentage": 84, "average_view_duration_sec": 18, "analytics_fetched_at": "2026-10-01T00:00:00Z"},
        {"topic": "Pourquoi le sommeil change-t-il les rêves ?", "views": 140, "average_view_percentage": 80, "average_view_duration_sec": 19, "analytics_fetched_at": "2026-10-02T00:00:00Z"},
        {"topic": "Pourquoi le téléphone coupe la concentration ?", "views": 130, "average_view_percentage": 25, "average_view_duration_sec": 7, "analytics_fetched_at": "2026-10-03T00:00:00Z"},
        {"topic": "Pourquoi le téléphone attire ton attention ?", "views": 160, "average_view_percentage": 30, "average_view_duration_sec": 8, "analytics_fetched_at": "2026-10-04T00:00:00Z"},
        {"topic": "Sommeil prédit", "views": 500, "predicted_retention": 0.99},
    ]
    sleep_bonus = _topic_retention_bonus("Pourquoi le sommeil aide-t-il le cerveau ?", history)
    phone_bonus = _topic_retention_bonus("Pourquoi le téléphone attire ton attention ?", history)
    assert sleep_bonus > phone_bonus
    assert sleep_bonus > 0