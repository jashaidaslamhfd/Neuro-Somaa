"""Dynamic posting slots for a France / francophone audience.

Static defaults are kept as a safe fallback, but the scheduler can now read
`data/upload_slot_intel_fr.json`, generated from real channel analytics, so the
pipeline publishes at the Paris slots that have actually produced the most
views/retention for this channel.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import ClassVar

import pytz


class FrancePeakTimeScheduler:
    # Three slots per France weekday, converted from the user's YouTube
    # heatmap shown in Pakistan local time (GMT+05:00). During CEST,
    # France is three hours behind Pakistan; Europe/Paris below handles the
    # CET/CEST transition automatically. Slots are intentionally explicit by
    # weekday because the heatmap is not identical across all seven columns.
    DEFAULT_WEEKDAY_PEAK_TIMES: ClassVar[dict] = {
        # Monday: PKT Mon 19:00, 21:00 and Tue 00:00 -> France Mon 16:00, 18:00, 21:00
        0: (
            {"hour": 16, "minute": 0, "name": "Heatmap lundi 16:00"},
            {"hour": 18, "minute": 0, "name": "Heatmap lundi 18:00"},
            {"hour": 21, "minute": 0, "name": "Heatmap lundi 21:00"},
        ),
        1: (
            {"hour": 16, "minute": 0, "name": "Heatmap mardi 16:00"},
            {"hour": 19, "minute": 0, "name": "Heatmap mardi 19:00"},
            {"hour": 21, "minute": 0, "name": "Heatmap mardi 21:00"},
        ),
        2: (
            {"hour": 16, "minute": 0, "name": "Heatmap mercredi 16:00"},
            {"hour": 18, "minute": 0, "name": "Heatmap mercredi 18:00"},
            {"hour": 21, "minute": 0, "name": "Heatmap mercredi 21:00"},
        ),
        3: (
            {"hour": 16, "minute": 0, "name": "Heatmap jeudi 16:00"},
            {"hour": 19, "minute": 0, "name": "Heatmap jeudi 19:00"},
            {"hour": 21, "minute": 0, "name": "Heatmap jeudi 21:00"},
        ),
        4: (
            {"hour": 17, "minute": 0, "name": "Heatmap vendredi 17:00"},
            {"hour": 19, "minute": 0, "name": "Heatmap vendredi 19:00"},
            {"hour": 21, "minute": 0, "name": "Heatmap vendredi 21:00"},
        ),
        5: (
            {"hour": 17, "minute": 0, "name": "Heatmap samedi 17:00"},
            {"hour": 19, "minute": 0, "name": "Heatmap samedi 19:00"},
            {"hour": 22, "minute": 0, "name": "Heatmap samedi 22:00"},
        ),
        6: (
            {"hour": 16, "minute": 0, "name": "Heatmap dimanche 16:00"},
            {"hour": 18, "minute": 0, "name": "Heatmap dimanche 18:00"},
            {"hour": 20, "minute": 0, "name": "Heatmap dimanche 20:00"},
        ),
    }
    DEFAULT_PEAK_TIMES = DEFAULT_WEEKDAY_PEAK_TIMES[0]

    def __init__(self):
        # 2026-08-12 truth sweep: honour PUBLISH_TIMEZONE from the workflow
        # instead of a second hardcoded copy (was blind config drift risk).
        self.paris_tz = pytz.timezone(os.environ.get("PUBLISH_TIMEZONE", "Europe/Paris"))
        self.utc_tz = pytz.UTC

    def _dynamic_peak_times(self) -> list[dict]:
        """Return learned peak slots, or [] when unavailable/disabled.

        Expected file schema (`scripts/premium_growth_loop.py` writes it):
        {
          "recommended_slots": [
            {"hour": 19, "minute": 30, "name": "Dynamic #1", "score": 3.2}
          ]
        }
        """
        if os.environ.get("USE_DYNAMIC_SCHEDULE", "true").strip().lower() == "false":
            return []
        path = os.environ.get("DYNAMIC_SCHEDULE_PATH", "data/upload_slot_intel_fr.json")
        try:
            if not os.path.exists(path):
                return []
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
            raw_slots = data.get("recommended_slots") or data.get("slots") or []
        except (OSError, json.JSONDecodeError):
            return []

        slots: list[dict] = []
        seen: set[tuple[int, int]] = set()
        max_slots = int(os.environ.get("DYNAMIC_SCHEDULE_SLOT_COUNT", "2"))
        # The generated file keeps recommended_slots in discovery order, not
        # score order. Rank by the learned score before applying the two-slot
        # cap, otherwise a lower-scoring 17:30 slot can displace 21:30.
        raw_slots = sorted(
            raw_slots,
            key=lambda item: float(item.get("score", float("-inf")))
            if isinstance(item, dict)
            else float("-inf"),
            reverse=True,
        )
        for item in raw_slots:
            try:
                hour = int(item.get("hour"))
                minute = int(item.get("minute", 0))
            except (TypeError, ValueError, AttributeError):
                continue
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                continue
            key = (hour, minute)
            if key in seen:
                continue
            seen.add(key)
            slots.append(
                {
                    "hour": hour,
                    "minute": minute,
                    "name": str(
                        item.get("name") or item.get("label") or f"Dynamique {hour:02d}:{minute:02d}"
                    ),
                    "score": item.get("score"),
                    "samples": item.get("samples", 0),
                    "dynamic": True,
                }
            )
            if len(slots) >= max_slots:
                break
        # Schedule should be chronological within the day so two daily runs
        # fill the learned slots without reintroducing the removed third slot.
        return sorted(slots, key=lambda slot: (slot["hour"], slot["minute"]))

    def _slots_for_weekday(self, weekday: int) -> tuple[dict, ...]:
        dynamic = self._dynamic_peak_times()
        return tuple(dynamic) if dynamic else self.DEFAULT_WEEKDAY_PEAK_TIMES[weekday]

    @property
    def peak_times(self) -> tuple[dict, ...]:
        # Backwards-compatible view for callers that do not provide a date.
        return self._slots_for_weekday(0)

    # Backwards compatibility for tests/imports that read PEAK_TIMES directly.
    PEAK_TIMES = DEFAULT_PEAK_TIMES

    def get_next_posting_times(self, count=3):
        now = datetime.now(self.paris_tz)
        result = []
        # Look ahead long enough that a claimed slot today can move a run to the
        # next learned slot tomorrow. Existing uploader lookahead asks for 12.
        for day in range(7):
            base_date = (now + timedelta(days=day)).date()
            for slot in self._slots_for_weekday(base_date.weekday()):
                when = self.paris_tz.localize(
                    datetime.combine(base_date, datetime.min.time()).replace(
                        hour=slot["hour"], minute=slot["minute"]
                    )
                )
                if when > now:
                    reason = (
                        "Créneau appris depuis les performances YouTube réelles"
                        if slot.get("dynamic")
                        else "Créneau de consultation France / francophonie"
                    )
                    result.append(
                        {
                            "time_paris": when.strftime("%Y-%m-%d %H:%M %Z"),
                            "time_utc": when.astimezone(self.utc_tz).isoformat(),
                            "peak_name": slot["name"],
                            "reason": reason,
                            "dynamic_score": slot.get("score"),
                            "dynamic_samples": slot.get("samples"),
                        }
                    )
        return result[:count]

    def get_scheduled_publish_settings(self, posting_time):
        return {
            "publishAt": posting_time.astimezone(self.utc_tz).isoformat(),
            "privacyStatus": "private",
            "timezone": "Europe/Paris",
            "localTime": posting_time.astimezone(self.paris_tz).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def validate_posting_interval(self, last_post_time):
        return (datetime.now(pytz.UTC) - last_post_time.astimezone(pytz.UTC)).total_seconds() >= 7200


USAPeakTimeScheduler = FrancePeakTimeScheduler
