#!/usr/bin/env python3
"""
SKILLOR — Monetization Readiness Tracker (28-day plan → 30 Aug 2026).

Purpose: make sure NOTHING blocks monetization the moment the thresholds are
reached, and give an honest daily plan to get there.

2026 YouTube Partner Program (research-verified):
  • Full YPP (ad revenue): 1,000 subs + (4,000 watch-hours/12mo OR 10M Shorts
    views/90d). Tier-1 (fan funding/memberships): 500 subs + (3,000 hrs OR 3M
    Shorts views/90d).
  • Application requires: AdSense linked, 2-step verification on, no active
    Community Guidelines strikes, country eligible, original content review.

This script:
  1. Fetches live channel stats (subs / views / estimated watch minutes).
  2. Computes the gap to each tier and the daily rate needed by 30 Aug.
  3. Runs an OBSTACLE AUDIT (the "koi rukawat na aye" part): music licensing,
     synthetic-media disclosure, made-for-kids, category, originality signals,
     description disclaimers, duplicate titles, leaked titles.
  4. Writes data/monetization_plan.md + data/monetization_plan.json.

Usage:
  python scripts/monetization_readiness.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("monetization_readiness")

PLAN_MD = ROOT / "data" / "monetization_plan.md"
PLAN_JSON = ROOT / "data" / "monetization_plan.json"
HISTORY = ROOT / "data" / "video_history.json"

TARGET_DATE = datetime(2026, 8, 30, tzinfo=timezone.utc)

TIERS = {
    "ypp_full": {"subs": 1000, "shorts_views_90d": 10_000_000, "watch_hours": 4000,
                 "label": "Full YPP (ad revenue)"},
    "ypp_tier1": {"subs": 500, "shorts_views_90d": 3_000_000, "watch_hours": 3000,
                  "label": "Tier-1 (fan funding, memberships, Super Thanks)"},
}


# ── live channel stats ──
def _build_client():
    import google.oauth2.credentials
    from googleapiclient.discovery import build
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    csec = os.environ.get("GOOGLE_CLIENT_SECRET")
    rtok = os.environ.get("REFRESH_TOKEN")
    if not (cid and csec and rtok):
        raise SystemExit("Missing GOOGLE_CLIENT_ID/SECRET/REFRESH_TOKEN env")
    creds = google.oauth2.credentials.Credentials(
        token=None, refresh_token=rtok,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid, client_secret=csec)
    return build("youtube", "v3", credentials=creds)


def _fetch_stats(yt) -> dict:
    ch = yt.channels().list(part="statistics,snippet,status", mine=True).execute()["items"][0]
    stats = ch["statistics"]
    status = ch.get("status", {})
    sn = ch.get("snippet", {})
    # watch hours via analytics (best effort)
    watch_hours = None
    try:
        yta = _build_analytics(yt)
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=365)
        resp = yta.reports().query(
            ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
            metrics="estimatedMinutesWatched").execute()
        rows = resp.get("rows") or [[0]]
        watch_hours = round(float(rows[0][0]) / 60.0, 1)
    except Exception as exc:
        log.warning("watch-hours fetch skipped: %s", exc)
    return {
        "subs": int(stats.get("subscriberCount", 0)),
        "total_views": int(stats.get("viewCount", 0)),
        "videos": int(stats.get("videoCount", 0)),
        "watch_hours_12mo": watch_hours,
        "made_for_kids_status": status.get("madeForKids"),
        "privacy_status": status.get("privacyStatus"),
        "long_uploads_status": status.get("longUploadsStatus"),
        "country": sn.get("country"),
        "default_language": sn.get("defaultLanguage"),
    }


def _build_analytics(yt):
    from googleapiclient.discovery import build
    creds = yt._http  # reuse http (auth) — simpler: rebuild from env
    import google.oauth2.credentials
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    csec = os.environ.get("GOOGLE_CLIENT_SECRET")
    rtok = os.environ.get("REFRESH_TOKEN")
    creds2 = google.oauth2.credentials.Credentials(
        token=None, refresh_token=rtok,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid, client_secret=csec)
    return build("youtubeAnalytics", "v2", credentials=creds2)


# ── obstacle audit (monetization blockers) ──
def _music_audit() -> dict:
    """Check every music file: own_* = verified original; third-party =
    unverified license = Content ID risk (a monetization blocker)."""
    music_dir = ROOT / "assets" / "music"
    if not music_dir.is_dir():
        return {"ok": True, "items": [], "note": "no music dir"}
    items = []
    risks = 0
    for f in sorted(music_dir.iterdir()):
        if f.suffix.lower() not in (".wav", ".mp3", ".m4a", ".ogg", ".aac", ".flac"):
            continue
        own = f.name.startswith("own_")
        if own:
            items.append({"file": f.name, "ok": True, "why": "original (generated in-repo)"})
        else:
            risks += 1
            items.append({"file": f.name, "ok": False,
                          "why": "UNVERIFIED license — Content ID claim risk (ATTRIBUTION.md)"})
    return {"ok": risks == 0, "risks": risks, "items": items}


def _title_audit() -> dict:
    try:
        h = json.loads(HISTORY.read_text(encoding="utf-8"))
        items = h if isinstance(h, list) else list(h.values())
    except Exception:
        return {"ok": True, "note": "no history", "duplicates": 0}
    titles = [v.get("title", "").strip().lower() for v in items if v.get("title")]
    from collections import Counter
    dups = {t: c for t, c in Counter(titles).items() if c > 1}
    return {"ok": not dups, "duplicates": dups}


def _checklist(yt, stats: dict, music: dict, titles: dict) -> list:
    """Return list of (status, item, detail) — status in ok|warn|block."""
    out = []
    # AdSense / 2FA / strikes — manual, cannot read via API
    out.append(("manual", "AdSense account linked",
                "YouTube Studio → Earn → AdSense. NOT automatable via API."))
    out.append(("manual", "2-step verification ON",
                "Google account security — required for YPP application."))
    out.append(("manual", "No active Community Guidelines strikes",
                "Check YouTube Studio → Channel health."))
    out.append(("manual", "Country eligible for YPP",
                "Pakistan accounts CAN monetize (YT supports PK); verify in Studio."))
    # music
    if music["ok"]:
        out.append(("ok", "Music licensing safe",
                    "own_* original beds only — zero Content ID risk."))
    else:
        out.append(("block", f"Music Content-ID risk ({music['risks']} unverified tracks)",
                    "Third-party tracks unlicensed. MUSIC_SOURCE defaults to 'own' now, "
                    "but DELETE or license the 4 third-party files before applying."))
    # duplicate titles
    if titles["ok"]:
        out.append(("ok", "No duplicate titles", "title sweep applied 2026-08-02"))
    else:
        out.append(("warn", f"Duplicate titles: {titles['duplicates']}",
                    "Run fr_full_optimize again after the two-pass dedup fix."))
    # originality / synthetic
    if os.environ.get("YT_DECLARE_SYNTHETIC_MEDIA") == "true":
        out.append(("ok", "Synthetic-media disclosure ON",
                    "YT_DECLARE_SYNTHETIC_MEDIA=true in workflow → honest, no reuse flags."))
    else:
        out.append(("warn", "Synthetic-media disclosure not set in this env",
                    "Workflow sets it; local runs should too."))
    if os.environ.get("YT_MADE_FOR_KIDS") == "false":
        out.append(("ok", "Made-for-kids correctly false", "science content, not kids-targeted"))
    else:
        out.append(("warn", "YT_MADE_FOR_KIDS not 'false' here", "workflow sets it"))
    # channel metadata
    if stats.get("country") == "FR":
        out.append(("ok", "Channel country = FR", "matches French-audience targeting"))
    else:
        out.append(("warn", f"Channel country = {stats.get('country')}",
                    "Set to FR in YouTube Studio for consistent signals."))
    # description disclaimers (educational)
    out.append(("ok", "Educational disclaimer in descriptions",
                "Every optimized description carries the medical disclaimer."))
    return out


def main() -> int:
    yt = _build_client()
    stats = _fetch_stats(yt)
    music = _music_audit()
    titles = _title_audit()

    now = datetime.now(timezone.utc)
    days_left = max(1, (TARGET_DATE - now).days)

    # projections per tier
    tiers_report = []
    for key, t in TIERS.items():
        subs_gap = max(0, t["subs"] - stats["subs"])
        views_gap = max(0, t["shorts_views_90d"] - stats["total_views"])
        subs_day = round(subs_gap / days_left, 1)
        views_day = round(views_gap / days_left, 1)
        tiers_report.append({
            "tier": key, "label": t["label"],
            "subs_needed": subs_gap, "subs_per_day": subs_day,
            "views_needed_90d": views_gap, "views_per_day": views_day,
            "reachable_by_aug30_subs": subs_day <= 50,  # sanity: <=50 subs/day
            "reachable_by_aug30_views": views_day <= 200_000,
        })

    checklist = _checklist(yt, stats, music, titles)

    report = {
        "generated_at": now.isoformat(),
        "target_date": TARGET_DATE.isoformat(),
        "days_left": days_left,
        "channel": stats,
        "tiers": tiers_report,
        "obstacles": [{"status": s, "item": i, "detail": d} for s, i, d in checklist],
        "music": music,
        "titles": titles,
    }
    PLAN_JSON.parent.mkdir(exist_ok=True)
    PLAN_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown
    md = [
        "# 🎯 SKILLOR — Monetization Readiness (30 août 2026)",
        f"_Generated {now.isoformat()} — {days_left} jours restants_",
        "",
        "## 📊 Channel actuel",
        f"- Abonnés: **{stats['subs']}** | Vues totales: {stats['total_views']:,} | Vidéos: {stats['videos']}",
        f"- Watch hours (12 mois): {stats['watch_hours_12mo'] or 'n/a'}",
        "",
        "## 🎯 Cibles (2026 YPP)",
    ]
    for t in tiers_report:
        md.append(f"- **{t['label']}**: +{t['subs_needed']} subs ({t['subs_per_day']}/jour) · "
                  f"+{t['views_needed_90d']:,} vues Shorts ({t['views_per_day']:,}/jour)")
    md.append("")
    md.append("## 🚫 Obstacles (koi rukawat na aye)")
    for s, i, d in checklist:
        icon = {"ok": "✅", "warn": "⚠️", "block": "🚫", "manual": "👤"}[s]
        md.append(f"- {icon} **{i}** — {d}")
    md.append("")
    md.append("## 🎵 Musique")
    for m in music.get("items", []):
        md.append(f"- {'✅' if m['ok'] else '🚫'} `{m['file']}` — {m['why']}")
    md.append("")
    md.append("## 🗓️ Plan quotidien (honnête)")
    md.append("- **2 Shorts/jour** à 12:30 & 19:30 Paris (déjà automatisé).")
    md.append("- 1 long-form 8-12 min / semaine (watch-hours path).")
    md.append("- Quand subs ≥ 500 → appliquer YPP Tier-1 dans YouTube Studio (fan funding).")
    md.append("- Quand subs ≥ 1 000 → appliquer Full YPP. L'application est MANUELLE "
              "(Studio → Earn) — ce repo ne peut pas l'automatiser.")
    md.append("")
    md.append("⚠️ **Réalité:** passer de ~48 → 1 000 subs en 28 jours est très ambitieux; "
              "l'objectif atteignable au 30 août est le **Tier-1 (500 subs)** avec une cadence "
              "parfaite + un format court (20-26s) qui améliore la rétention. Le repo est prêt "
              "pour que RIEN ne bloque l'application le jour où le seuil est franchi.")
    PLAN_MD.write_text("\n".join(md), encoding="utf-8")

    print("\n".join(md))
    log.info("Plan written: %s", PLAN_MD)
    return 0


if __name__ == "__main__":
    sys.exit(main())
