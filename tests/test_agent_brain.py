from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from agent_brain import AgentBrain


def test_agent_brain_initialization(tmp_path: Path):
    agent = AgentBrain(data_dir=tmp_path)
    assert agent.memory["version"] == "2.0.0"
    assert "strategy" in agent.memory
    assert agent.memory["strategy"]["max_title_chars"] == 42


def test_agent_reasoning_and_reflection(tmp_path: Path):
    agent = AgentBrain(data_dir=tmp_path)
    topic = "Pourquoi ton cerveau adore-t-il procrastiner ?"
    plan = agent.reason_and_strategize(topic)
    assert "cerveau" in plan["detected_keywords"]
    assert plan["title_length_cap"] == 42

    production_mock = {
        "title": "Pourquoi ton cerveau procrastine ?",
        "topic": topic,
        "duration": 18.5,
        "hook_score": 95,
        "quality_score": 90,
        "status": "uploaded",
        "url": "https://youtu.be/mock123"
    }

    agent.reflect_and_learn(production_mock, plan)
    assert agent.memory["total_cycles"] == 1
    assert len(agent.memory["performance_records"]) == 1
    assert "Pourquoi ton cerveau procrastine ?" in agent.memory["winning_hooks"]


def test_agent_brain_audit_and_retention(tmp_path: Path):
    agent = AgentBrain(data_dir=tmp_path)
    script = {
        "title": "Pourquoi ton corps sursaute ?",
        "scenes": [
            {"caption": "Ton corps sursaute.", "narration": "Au moment de t endormir ton corps sursaute violemment."},
            {"caption": "Signal sensoriel.", "narration": "Tes neurones interpretent le sommeil comme une chute libre."},
            {"caption": "Reflexe archaique.", "narration": "Un circuit cerebral ancestral prend les commandes avant la conscience."},
            {"caption": "Spasme hypnique.", "narration": "Les neuroscientifiques appellent ce declic un sursaut hypnique."},
            {"caption": "Impulsion motrice.", "narration": "Pour te sauver de cette chute le cortex moteur envoie une decharge."},
            {"caption": "Panique inconsciente.", "narration": "Rien de dangereux mais ton inconscient panique un court instant."},
            {"caption": "Transition nerveuse.", "narration": "Tu as surpris ton systeme nerveux en plein changement d etat."},
            {"caption": "La boucle.", "narration": "Voila pourquoi ton corps sursaute a chaque fois."}
        ]
    }
    audit = agent.audit_script(script)
    assert audit["passed"] is True
    assert audit["predicted_str_pct"] is None
    assert audit["heuristic_hook_score_pct"] >= 70.0
    assert 35.0 <= audit["predicted_apv_pct"] <= 65.0
    assert audit["score_type"] == "heuristic_script_score_not_actual_audience_retention"
    assert audit["apv_estimate_basis"] == "generic_heuristic_no_analytics"

    optimized = agent.optimize_script(script)
    assert "retention_verdict" in optimized

    curve = agent.simulate_retention_curve(script)
    assert len(curve) == 19
    assert curve[0]["retention_pct"] == 100.0


def test_local_analytics_uses_observed_watch_metrics_only(tmp_path: Path, monkeypatch):
    import json

    (tmp_path / "video_history.json").write_text(json.dumps([
        {
            "title": "Faible échantillon",
            "views": 8,
            "average_view_percentage": 99,
            "average_view_duration_sec": 15,
            "analytics_fetched_at": "2026-10-01T00:00:00Z",
        },
        {
            "title": "Bonne rétention",
            "topic": "Pourquoi la mémoire fonctionne",
            "views": 120,
            "average_view_percentage": 82.5,
            "average_view_duration_sec": 18,
            "analytics_fetched_at": "2026-10-02T00:00:00Z",
        },
        {
            "title": "Prédiction uniquement",
            "views": 500,
            "predicted_retention": 0.99,
        },
    ]), encoding="utf-8")
    agent = AgentBrain(data_dir=tmp_path)
    snapshot = agent._local_analytics_snapshot()
    assert snapshot["videos_with_usable_analytics"] == 1
    assert snapshot["best_observed_video"]["title"] == "Bonne rétention"
    assert snapshot["mean_average_view_percentage"] == 82.5


def test_sense_uses_local_analytics_without_oauth(tmp_path: Path, monkeypatch):
    import json

    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "REFRESH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "video_history.json").write_text(json.dumps([{
        "title": "Rétention observée",
        "topic": "Pourquoi le cerveau retient une chanson",
        "views": 80,
        "average_view_percentage": 71,
        "average_view_duration_sec": 17,
        "analytics_fetched_at": "2026-10-02T00:00:00Z",
    }]), encoding="utf-8")
    metrics = AgentBrain(data_dir=tmp_path).sense_youtube_performance()
    assert metrics["sync_status"] == "local_history_only"
    assert metrics["learning_mode"] == "local_observed_analytics"
    assert metrics["local_analytics"]["videos_with_usable_analytics"] == 1