from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from youtube import _next_publish_time


def test_requested_future_slot_is_kept():
    zone = ZoneInfo("Europe/Paris")
    now = datetime(2026, 10, 9, 14, 0, tzinfo=zone)
    assert _next_publish_time(now, "14:30") == datetime(2026, 10, 9, 14, 30, tzinfo=zone)


def test_late_job_uses_next_remaining_slot_same_day():
    zone = ZoneInfo("Europe/Paris")
    now = datetime(2026, 10, 9, 14, 35, tzinfo=zone)
    assert _next_publish_time(now, "14:30") == datetime(2026, 10, 9, 17, 30, tzinfo=zone)


def test_after_last_slot_rolls_to_first_slot_tomorrow():
    zone = ZoneInfo("Europe/Paris")
    now = datetime(2026, 10, 9, 20, 5, tzinfo=zone)
    assert _next_publish_time(now, "20:00") == datetime(2026, 10, 10, 14, 30, tzinfo=zone)


def test_invalid_slot_falls_forward_safely():
    zone = ZoneInfo("Europe/Paris")
    now = datetime(2026, 10, 9, 16, 0, tzinfo=zone)
    assert _next_publish_time(now, "25:99") == datetime(2026, 10, 9, 17, 30, tzinfo=zone)
