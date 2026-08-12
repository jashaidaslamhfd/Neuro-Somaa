#!/usr/bin/env python3
"""Assemble the intelligence report (JSON + markdown dashboard).

Outputs:
  data/intelligence_report.json       (rolling, machine-consumed)
  data/intelligence_dashboard_latest.md (rolling, human-consumed)

Both are ROLLING files (never dated) so the snapshot pruner never needs to
manage them — the daily sync simply overwrites.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def _retention_distribution(history: list[dict]) -> dict:
    vals = []
    for e in history or []:
        v = e.get("average_view_percentage")
        try:
            if v is not None:
                vals.append(float(v))
        except (TypeError, ValueError):
            continue
    if len(vals) < 8:
        return {"reliable": False, "n": len(vals)}
    vals.sort()
    n = len(vals)

    def pct(p: float) -> float:
        i = min(n - 1, max(0, round(p * (n - 1))))
        return round(vals[i], 1)

    below_50 = sum(1 for v in vals if v < 50) / n
    return {
        "reliable": True, "n": n,
        "p10": pct(0.10), "p50": pct(0.50), "p90": pct(0.90),
        "share_below_50pct": round(below_50, 3),
        "note": "share_below_50pct = fraction of videos losing the average "
                "viewer before half the Short — the 4-9s hook cliff lives here.",
    }


def _data_quality(history: list[dict]) -> dict:
    vids = [e for e in history or [] if e.get("views") is not None]
    ctr = sum(1 for e in vids if e.get("actual_ctr") is not None)
    reten = sum(1 for e in vids if e.get("average_view_percentage") is not None)
    return {
        "videos_with_views": len(vids),
        "ctr_coverage": round(ctr / max(len(vids), 1), 3),
        "retention_coverage": round(reten / max(len(vids), 1), 3),
        "ctr_gap": "0 coverage → YouTube Analytics scope/ metric must be fixed "
                   "(see 2026-08-11 audit fix; token needs yt-analytics.readonly)"
                   if ctr == 0 else "ok",
    }


def build_markdown(report: dict) -> str:
    dq = report["data_quality"]
    models = report["models"]["ridge"]
    bandit = report["bandit"]
    anoms = report["anomalies"]
    fc = report["forecast"]
    clusters = report["clusters"]

    lines = [
        "# 🧠 Neuro-Somaa — Intelligence Dashboard",
        f"_{report['generated_at']}_ — n={report['n_videos_analyzed']} vidéos réelles",
        "",
        "## 📊 Data quality",
        f"- vues réelles: **{dq['videos_with_views']}** · couverture CTR: **{dq['ctr_coverage']:.0%}** · rétention: **{dq['retention_coverage']:.0%}**",
    ]
    if dq.get("ctr_gap") and "0 coverage" in str(dq.get("ctr_gap", "")):
        lines.append(f"- ⚠️ {dq['ctr_gap']}")

    # Truth Gate FIRST in the dashboard — a reader must know which internal
    # numbers deserve trust before reading any of them.
    if report.get("truth_gate"):
        from .truth_gate import render_truth_markdown
        lines += render_truth_markdown(report["truth_gate"])

    lines += ["", "## 🤖 Modèles (ridge + MLP, validation croisée)"]
    if models.get("cv_r2_mean") is not None:
        lines.append(f"- ridge log-vues: **R²_cv = {models['cv_r2_mean']} ± {models['cv_r2_std']}** (MAE ≈ {models['cv_mae_views']} vues) — {'✅ fiable' if models.get('reliable') else '⚠️ bruit, conseils seulement'}")
        top = ", ".join(f"`{f['feature']}` ({f['direction']})" for f in models.get("top_features", [])[:5])
        lines.append(f"- facteurs dominants: {top}")
    else:
        lines.append(f"- ridge: {models.get('reason', 'indisponible')}")
    mlp = report["models"].get("mlp", {})
    lines.append(f"- MLP: {'MAE ≈ ' + str(mlp.get('in_sample_mae_views')) + ' vues (advisory)' if mlp.get('in_sample_mae_views') else mlp.get('reason', 'n/a')}")

    lines += ["", "## 🎰 Bandit de titres (Thompson sampling)"]
    rec = bandit.get("recommended_pattern")
    if rec:
        lines.append(f"- ✅ pattern recommandé: **{rec['pattern']}** (winner-rate {rec['thompson_score']}, avg {rec['avg_views']} vues)")
    for name, arm in list(bandit.get("arms", {}).items())[:5]:
        badge = "✅" if arm["confident"] else "🔬"
        lines.append(f"  {badge} `{name:12s}` n={arm['n']:>2} · winner-rate {arm['winner_rate']:.0%} · avg {arm['avg_views']}")

    lines += ["", f"## 🚨 Anomalies ({anoms.get('method', 'n/a')})"] if anoms.get("reliable") else ["", f"## 🚨 Anomalies — {anoms.get('reason', 'n/a')}"]
    for a in anoms.get("anomalies", [])[:5]:
        icon = "🚀" if a["direction"] == "over" else "🔻"
        lines.append(f"- {icon} **{a['title']}** — {a['views']} vues (z={a['modified_z']}): _{a['action']}_")

    if fc.get("reliable"):
        lines += ["", "## 📈 Prévision 30 jours (Holt)"]
        lines.append(f"- tendance: **{fc['daily_trend']:+.1f} vues/jour^²** · attendu 30j: **{fc['total_30d_expected']:.0f} vues** (bande {fc['band_30d_low']}–{fc['band_30d_high']}/j)")
    else:
        lines += ["", f"## 📈 Prévision — {fc.get('reason', 'n/a')}"]

    if clusters.get("reliable"):
        lines += ["", f"## 🗂️ Clusters de sujets (k={clusters['k']}) — gagnant: **{clusters['winner_cluster']}**"]
        for c in clusters["clusters"][:5]:
            lines.append(f"- `{c['name']}` — {c['size']} vidéos · avg {c['avg_views']} vues · max {c['max_views']}")

    ret = report.get("retention", {})
    if ret.get("reliable"):
        lines += ["", "## ⏱️ Rétention",
                  f"- P10/P50/P90 = {ret['p10']}% / {ret['p50']}% / {ret['p90']}% · **{ret['share_below_50pct']:.0%}** des vidéos perdent le spectateur avant la moitié"]

    exp = report.get("experiment", {})
    if exp.get("available"):
        verdict = f"**{exp['winner']}** gagne" if exp.get("winner") else "pas de différence significative encore"
        lines += ["", f"## 🧪 Expérience durée: {verdict} (p={exp.get('p_value')})",
                  f"- `{exp['arm_a']}` avg {exp['mean_a']} vs `{exp['arm_b']}` avg {exp['mean_b']} (n={exp['n_a']}/{exp['n_b']})"]

    ha = report.get("hook_arms", {})
    if ha.get("available"):
        lead = ha.get("leading_arm", {})
        lines += ["", f"## 🪝 Expérience hooks — leader actuel: **{lead.get('arm')}** (avg {lead.get('avg_views')} vues)"]
        for p in ha.get("pairwise", []):
            tag = f"p={p['p_value']}" + (" ✅" if p.get("significant") else " (ns)")
            lines.append(f"- `{p['a']}` ({p['mean_a']}) vs `{p['b']}` ({p['mean_b']}) — {tag}")
    else:
        lines += ["", "## 🪝 Expérience hooks — " + ha.get("reason", "en attente")]

    fl = report.get("viral_fastlane", {})
    if fl.get("entries"):
        lines += ["", f"## 🚀 Winner-cloning fastlane ({fl['entries']} sujets, TTL {fl['ttl_hours']}h)"]
        for item in fl.get("items", [])[:5]:
            src = item.get("cloned_from", {})
            lines.append(f"- « {item['topic']} » ← cloné de **{src.get('views')} vues**")
        lines.append("_Le prochain run de génération pioche D'ABORD dans cette file._")

    lines += ["", "_Méthodes: ridge closed-form + MLP numpy (k-fold CV), Thompson Beta/Gaussien, z-score MAD, Holt, TF-IDF k-means++, test de permutation. Toutes les métriques montrent leur honnêteté — aucun chiffre n'est publié sans sa barre d'échantillons._"]
    return "\n".join(lines) + "\n"


def write_reports(report: dict) -> dict:
    DATA.mkdir(exist_ok=True)
    (DATA / "intelligence_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md = build_markdown(report)
    (DATA / "intelligence_dashboard_latest.md").write_text(md, encoding="utf-8")
    return {"json": str(DATA / "intelligence_report.json"),
            "markdown": str(DATA / "intelligence_dashboard_latest.md"),
            "bytes": len(md.encode("utf-8"))}
