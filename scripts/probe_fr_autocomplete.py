from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "autocomplete_probe_fr.json"
SEEDS = (
    "pourquoi mon corps",
    "pourquoi le cerveau",
    "pourquoi les yeux",
    "pourquoi je me réveille",
    "muscle qui tremble tout seul",
    "sommeil paradoxal",
)


def fetch_suggestions() -> list[dict]:
    responses: list[dict] = []
    for seed in SEEDS:
        url = f"https://suggestqueries.google.com/complete/search?client=firefox&hl=fr&gl=fr&q={quote(seed)}"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        suggestions = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        responses.append({"seed": seed, "url": url, "suggestions": suggestions})
    return responses


def main() -> int:
    responses = fetch_suggestions()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"fetched_at_utc": datetime.now(UTC).isoformat(), "locale": "fr-FR", "responses": responses},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT} with {sum(len(item['suggestions']) for item in responses)} suggestions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
