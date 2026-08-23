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

import pytz


class FrancePeakTimeScheduler:
    DEFAULT_PEAK_TIMES = (
        {"hour": 17, "minute": 30, "name": "Dynamique 17:30"},
        {"hour": 19, "minute": 30, "name": "Dynamique 19:30"},
        {"hour": 21, "minute": 30, "name": "Dynamique 21:30"},
    )
    # France-first fallback: evening Paris slots match the learned
    # Europe/Paris performance file when dynamic analytics are unavailable.

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
        max_slots = int(os.environ.get("DYNAMIC_SCHEDULE_SLOT_COUNT", "3"))
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
        # Schedule should be chronological within the day so three daily runs
        # fill all learned slots instead of the morning run grabbing prime time.
        return sorted(slots, key=lambda slot: (slot["hour"], slot["minute"]))

    @property
    def peak_times(self) -> tuple[dict, ...]:
        dynamic = self._dynamic_peak_times()
        return tuple(dynamic) if dynamic else self.DEFAULT_PEAK_TIMES

    # Backwards compatibility for tests/imports that read PEAK_TIMES directly.
    PEAK_TIMES = DEFAULT_PEAK_TIMES

    def get_next_posting_times(self, count=3):
        now = datetime.now(self.paris_tz)
        result = []
        # Look ahead long enough that a claimed slot today can move a run to the
        # next learned slot tomorrow. Existing uploader lookahead asks for 12.
        for day in range(7):
            base_date = (now + timedelta(days=day)).date()
            for slot in self.peak_times:
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
