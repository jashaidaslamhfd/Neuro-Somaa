"""2026-08-17: guards against the rate-limit regex silently truncating
daily/hourly Groq quota waits to a useless few-minute default (root cause
of a day with zero videos produced: 'try again in 5h44m...' parsed as if
it were 'try again in 5m...').
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from script_generator import (
    MAX_RATE_LIMIT_SLEEP_SEC,
    _parse_groq_rate_limit_wait,
)


class GroqRateLimitWaitParsingTests(unittest.TestCase):
    def test_minutes_and_seconds(self):
        err = "Rate limit reached. Please try again in 45m12s."
        self.assertEqual(_parse_groq_rate_limit_wait(err), 45 * 60 + 12 + 10)

    def test_hours_minutes_seconds_with_decimals(self):
        err = "Rate limit reached for model on tokens per day (TPD). Please try again in 5h44m32.891s."
        expected = 5 * 3600 + 44 * 60 + 32 + 10
        self.assertEqual(_parse_groq_rate_limit_wait(err), expected)

    def test_days_hours_minutes_seconds(self):
        err = "Please try again in 1d2h15m3.2s."
        expected = 1 * 86400 + 2 * 3600 + 15 * 60 + 3 + 10
        self.assertEqual(_parse_groq_rate_limit_wait(err), expected)

    def test_seconds_only(self):
        err = "Please try again in 30s."
        self.assertEqual(_parse_groq_rate_limit_wait(err), 30 + 10)

    def test_unparseable_message_falls_back_to_default(self):
        err = "Rate limited, no timing info given."
        self.assertEqual(_parse_groq_rate_limit_wait(err, default_sec=300), 300)

    def test_long_quota_wait_exceeds_per_run_budget(self):
        # This is exactly the case that used to be silently truncated:
        # a daily-quota wait measured in hours must be recognised as
        # bigger than the per-run sleep budget so the caller fails fast
        # instead of blocking the job for hours.
        err = "Please try again in 5h44m32.891s."
        wait = _parse_groq_rate_limit_wait(err)
        self.assertGreater(wait, MAX_RATE_LIMIT_SLEEP_SEC)

    def test_short_burst_limit_stays_within_budget(self):
        err = "Please try again in 2m3s."
        wait = _parse_groq_rate_limit_wait(err)
        self.assertLess(wait, MAX_RATE_LIMIT_SLEEP_SEC)


if __name__ == "__main__":
    unittest.main()
