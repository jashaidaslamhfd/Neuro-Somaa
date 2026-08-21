#!/usr/bin/env python3
"""SKILLOR FR — LOCAL DRY-RUN of the video-creation pipeline (Phase 1b→4).

Groq key nahi hai sandbox mein, isliye script fixture (valid LLM-shaped dict)
use karta hai aur SEO → images → voice → video → quality gates ko end-to-end
chala kar verify karta hai. YouTube ko touch nahi karta.
"""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

os.environ.setdefault("TTS_ENGINE", "edge")
os.environ.setdefault("TARGET_MIN_SECONDS", "20")
os.environ.setdefault("TARGET_MAX_SECONDS", "26")

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dryrun")

# Valid French Body-Glitch script (matches script_generator schema)
SCRIPT = {
    "title": "Pourquoi la peau se fripe dans l'eau ?",
    "hook": "Votre peau se fripe dans l'eau depuis toujours.",
    "topic": "Pourquoi la peau se fripe dans l'eau",
    "category": "Corps",
    "cta": "Abonnez-vous pour la science simple.",
    "description": "Votre peau se fripe dans l'eau : la science du quotidien.",
    "scenes": [
        {"visual": "peau ridée sous l'eau", "caption": "Votre peau se fripe dans l'eau depuis toujours."},
        {
            "visual": "doigts froissés dans un bain",
            "caption": "Ce n'est pas l'eau qui entre dans la peau, c'est une réaction nerveuse.",
        },
        {
            "visual": "vaisseaux sanguins de la main",
            "caption": "Le système nerveux resserre les vaisseaux des doigts.",
        },
        {"visual": "science du corps humain", "caption": "Ce réflexe améliore la prise des objets mouillés."},
        {
            "visual": "cerveau et nerfs",
            "caption": "Une adaptation ancienne que le corps garde encore aujourd'hui.",
        },
        {"visual": "abonnement science", "caption": "Abonnez-vous pour la science simple."},
    ],
    "tags": ["peau", "eau", "science", "corps humain", "curiosité"],
}

results = {}


def check(name, fn):
    t0 = time.time()
    try:
        out = fn()
        results[name] = {"ok": True, "secs": round(time.time() - t0, 1)}
        print(f"  ✅ {name}  ({results[name]['secs']}s)")
        return out
    except Exception as e:
        results[name] = {"ok": False, "secs": round(time.time() - t0, 1), "err": str(e)[:200]}
        print(f"  ❌ {name}: {e}")
        return None


def main():
    print("=" * 60)
    print("SKILLOR FR — LOCAL DRY-RUN (no YouTube)")
    print("=" * 60)

    # Phase 1b: SEO package
    seo = check(
        "seo_generator", lambda: __import__("seo_generator").generate_seo_package(SCRIPT["topic"], SCRIPT)
    )
    if seo:
        print(f"       chosen_title: {seo['chosen_title']}")
        print(f"       title_options: {seo['title_options'][:3]}")
        print(f"       tags: {seo['tags'][:6]}")

    # Phase 2: images (procedural fallback)
    imgs = check(
        "image_generator",
        lambda: [
            __import__("image_generator").generate_scene_image(i, s, set(), set())
            for i, s in enumerate(SCRIPT["scenes"])
        ],
    )
    img_paths = [x["path"] for x in imgs] if imgs else []
    print(f"       images: {len(img_paths)} -> {img_paths[0] if img_paths else 'NONE'}")

    # Phase 3: voice (edge-tts)
    segs = check(
        "voice_generator",
        lambda: __import__("voice_generator").generate_voice_segments(
            SCRIPT["scenes"], output_dir="output/dryrun_voice"
        ),
    )
    narration = sum(s["duration"] for s in segs) if segs else 0
    print(f"       narration: {narration:.1f}s (target 17-24s)")
    wavs = [s["path"] for s in segs if s.get("path") and os.path.exists(s["path"])]
    print(f"       voice files: {len(wavs)}")

    # Phase 4: build video
    out = check(
        "video_editor.build_video",
        lambda: __import__("video_editor").build_video(
            img_paths, segs, SCRIPT["scenes"], output_path="output/dryrun_final.mp4"
        ),
    )
    if out and os.path.exists(out):
        size = os.path.getsize(out)
        print(f"       video: {out} ({size / 1e6:.1f} MB)")
        results["video_size_mb"] = round(size / 1e6, 1)

    # Quality gates
    print("\n--- QUALITY GATES ---")
    check(
        "french_quality_gate", lambda: __import__("french_quality_gate").validate_publication_quality(SCRIPT)
    )
    check(
        "quality_checker", lambda: __import__("quality_checker").QualityChecker().check_script_quality(SCRIPT)
    )
    check("anti_spam", lambda: __import__("anti_spam").AntiSpamSystem().check_script_for_spam(SCRIPT))
    check(
        "final_video_audit",
        lambda: __import__("final_video_audit").run_final_publication_audit(
            SCRIPT, {"video_path": out or "", "thumb_path": ""}
        ),
    )

    # summary
    print("\n" + "=" * 60)
    ok = sum(1 for r in results.values() if r.get("ok"))
    print(f"DRY-RUN SUMMARY: {ok}/{len(results)} passed")
    for k, r in results.items():
        if not r.get("ok"):
            print(f"  FAILED: {k} -> {r.get('err')}")
    print("=" * 60)
    return 0 if ok == len(results) else 2


if __name__ == "__main__":
    sys.exit(main())
