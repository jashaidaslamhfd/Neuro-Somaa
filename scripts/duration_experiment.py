#!/usr/bin/env python3
"""Expérience A/B sur la durée — la seule question encore ouverte.

CE QUI A DÉJÀ ÉTÉ ÉLIMINÉ (courbes de rétention seconde par seconde,
14 vidéos, 2026-07-26) :

  · l'accroche          — 101% des spectateurs sont encore là à 3s
  · le mot d'ouverture  — les 3 meilleures vidéos utilisent l'ouverture
                          « Vous avez… » que j'avais interdite
  · la phrase coupée    — les tronquées ont mieux retenu (n=2)
  · la réponse tardive  — les réponses tardives ont mieux retenu
  · une 2e question     — +1.1 pt, n=6 : du bruit
  · le contenu de la    — « explique » 33.0% vs « diffère » 33.0% :
    phrase 2              exactement zéro écart

La falaise touche 14/14 vidéos entre 4,6s et 9,0s quel que soit le texte.
La cause est donc le FORMAT, pas les mots.

CE QUI RESTE OUVERT : la durée. Les données actuelles ne peuvent pas
trancher car toutes les vidéos font 36-43s. Dans cette plage étroite, les
PLUS LONGUES gagnent (35,6% vs 31,6%) — ce qui contredit l'intuition
« faire plus court ». La régression donne des valeurs absurdes en dehors
de la plage observée (-8% à 20s), preuve qu'on extrapole dans le vide.

Ce script ne devine pas : il PLANIFIE un test. Il alterne TARGET_MIN/MAX
entre un bras court et un bras long, enregistre quel bras a produit quelle
vidéo, et compare la rétention une fois les données arrivées.

Usage :
  python scripts/duration_experiment.py --assign     # quel bras aujourd'hui
  python scripts/duration_experiment.py --report     # résultats à ce jour
"""
import argparse
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "duration_experiment.json"
HISTORY = ROOT / "data" / "video_history.json"
CURVES = ROOT / "data" / "swipe_curves.json"

# Bras courts vs longs. Le bras "long" reproduit le format actuel (témoin) ;
# le bras "court" descend juste sous la plage observée pour tester la
# direction, sans sauter à 20s où l'on n'a aucune donnée.
ARMS = {
    "control_long": {"min": 40, "max": 48},
    "test_short": {"min": 26, "max": 32},
}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def assign() -> int:
    """Alterne strictement pour équilibrer les bras."""
    state = _load(STATE, {"assignments": []})
    counts = dict.fromkeys(ARMS, 0)
    for record in state["assignments"]:
        counts[record["arm"]] = counts.get(record["arm"], 0) + 1
    arm = min(counts, key=lambda a: (counts[a], a))
    config = ARMS[arm]

    print(f"ARM={arm}")
    print(f"TARGET_MIN_SECONDS={config['min']}")
    print(f"TARGET_MAX_SECONDS={config['max']}")

    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as handle:
            handle.write(f"EXPERIMENT_ARM={arm}\n")
            handle.write(f"TARGET_MIN_SECONDS={config['min']}\n")
            handle.write(f"TARGET_MAX_SECONDS={config['max']}\n")
    return 0


def record(video_id: str, arm: str) -> int:
    state = _load(STATE, {"assignments": []})
    state["assignments"].append({"video_id": video_id, "arm": arm})
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"recorded {video_id} -> {arm}")
    return 0


def report() -> int:
    state = _load(STATE, {"assignments": []})
    history = {v.get("youtube_video_id"): v for v in _load(HISTORY, [])}
    curves = {v["video_id"]: v for v in _load(CURVES, {}).get("videos", [])}

    buckets = {}
    for record_entry in state["assignments"]:
        video = history.get(record_entry["video_id"])
        if not video or video.get("average_view_percentage") is None:
            continue
        curve = curves.get(record_entry["video_id"], {})
        buckets.setdefault(record_entry["arm"], []).append({
            "retention": video["average_view_percentage"],
            "views": video.get("views") or 0,
            "watched_s": (video["average_view_percentage"]
                          * curve.get("duration_s", 0) / 100) if curve else None,
        })

    if not buckets:
        print("Aucune vidéo assignée n'a encore de données de rétention.")
        print("Il faut environ 6-8 vidéos par bras (≈4-5 jours) avant de conclure.")
        return 0

    print(f"{'bras':<16} {'n':>3} {'rétention':>10} {'vues':>8} {'secondes vues':>14}")
    for arm, rows in sorted(buckets.items()):
        watched = [r["watched_s"] for r in rows if r["watched_s"]]
        print(f"{arm:<16} {len(rows):>3} "
              f"{statistics.mean(r['retention'] for r in rows):>9.1f}% "
              f"{statistics.mean(r['views'] for r in rows):>8.0f} "
              f"{statistics.mean(watched) if watched else 0:>13.1f}s")

    if len(buckets) == 2 and all(len(v) >= 5 for v in buckets.values()):
        arms = sorted(buckets)
        diff = (statistics.mean(r["retention"] for r in buckets[arms[1]])
                - statistics.mean(r["retention"] for r in buckets[arms[0]]))
        print(f"\nécart : {diff:+.1f} points ({arms[1]} vs {arms[0]})")
        if abs(diff) < 4:
            print("→ écart trop faible pour cet échantillon : pas de conclusion.")
        else:
            print(f"→ {arms[1] if diff > 0 else arms[0]} mène. Continuer jusqu'à n≥8 par bras.")
    else:
        print("\nPas encore assez de vidéos par bras (minimum 5) pour comparer.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assign", action="store_true")
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--record", nargs=2, metavar=("VIDEO_ID", "ARM"))
    parser.add_argument("--last-video-id", action="store_true",
                        help="print the newest uploaded video id (for CI)")
    args = parser.parse_args()

    if args.last_video_id:
        history = _load(HISTORY, [])
        print(history[-1].get("youtube_video_id") or "" if history else "")
        return 0
    if args.assign:
        return assign()
    if args.record:
        return record(*args.record)
    return report()


if __name__ == "__main__":
    sys.exit(main())
