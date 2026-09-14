from __future__ import annotations

import json
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
