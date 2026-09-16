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
    assert audit["predicted_str_pct"] >= 70.0
    assert audit["predicted_apv_pct"] >= 90.0

    optimized = agent.optimize_script(script)
    assert "retention_verdict" in optimized

    curve = agent.simulate_retention_curve(script)
    assert len(curve) == 19
    assert curve[0]["retention_pct"] == 100.0
