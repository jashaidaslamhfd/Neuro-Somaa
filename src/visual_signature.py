"""Visual signature system — "Le Labo Obscur" (Neuro-Somaa).

Every channel on YouTube uses the same generic stock footage. What makes a
channel *recognizable* is a fixed visual identity: one signature color world,
one signature scale, one signature motion language — applied consistently
across every video. That is what this module enforces.

Identity anchors (CHANNEL CONSTANT — identical in every video):
  - dark teal/ink medical-lab palette
  - macro biology scale (skin, muscle fibre, glowing neurons)
  - floating particle depth
  - single-subject documentary focus

Per-video variation (seeded by the video topic, deterministic):
  - one of six signature styles is picked per video, so the channel keeps
    its identity while no two videos look byte-for-byte identical.

The stock layers (Pexels/Pixabay) remain available as a *fallback only* —
they are license-safe (verified 2026-08-15) but generic; the signature world
is the default now.
"""

import logging
import random

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# CHANNEL IDENTITY — the fixed anchors that make Neuro-Somaa instantly
# recognizable in any frame. These are appended to every generated scene.
# --------------------------------------------------------------------------- #
SIGNATURE_IDENTITY = (
    # the world: one signature palette, never the generic "cinematic photo"
    "dark teal and ink-black medical laboratory aesthetic, deep ocean-teal "
    "color grade with ink shadows, single subject in sharp macro focus, "
    # the scale: biology up close, not stock-room wide shots
    "extreme close-up macro biology scale, visible organic texture, "
    "subsurface skin glow, "
    # the atmosphere: signature depth language
    "floating luminous particles drifting in darkness, shallow depth of field, "
    "atmospheric volumetric light from one side, "
    # quality + anti-AI-plasticity + content safety
    "hyper-detailed realistic rendering, natural organic imperfection, "
    "photorealistic scientific documentary, vertical composition, "
    "no text, no watermark, no logo, not blurry, no plastic skin, "
    "no blood, no gore, no wounds, no horror, no scary face, no zombie, "
    "no monster, no distorted anatomy, safe for all audiences, "
    "medically respectful, educational tone"
)

# Six signature styles — same identity world, different lighting/scene
# treatments. Picked deterministically from the video topic so one video is
# cohesive and the channel stays varied.
SIGNATURE_STYLES = [
    # 1: cold lab specimen — the clinical discovery shot
    "cold clinical specimen lighting, sterile glass-slide depth, "
    "crisp white key light on teal darkness, forensic clarity",
    # 2: living tissue glow — the inside-the-body shot
    "soft bioluminescent inner glow, translucent tissue translucency, "
    "warm ember core under cold teal surface, living texture",
    # 3: microscope world — the infinite-magnification shot
    "electron-microscope cinematic rendering, fibre and cell-wall detail, "
    "silver rim light, scientific instrument precision",
    # 4: neural night — the brain/mind shot
    "midnight neural network luminescence, synapse spark trails, "
    "deep indigo-teal gradient, quiet electrical energy",
    # 5: noir anatomy — the dramatic discovery shot
    "chiaroscuro noir anatomy, single dramatic beam through darkness, "
    "heavy shadow weight, museum-of-nature stillness",
    # 6: dawn biology — the calm revelation shot
    "soft dawn-grey natural window light meeting teal shadow, "
    "gentle morning atmosphere, calm scientific revelation, serene clarity",
]

_IDENTITY_TAIL = (
    "vertical composition, no text, no watermark, not blurry, no plastic skin, no distorted anatomy"
)


def pick(value: str, options: list):
    """Deterministic pick seeded by `value` — same topic always same style."""
    if not options:
        return ""
    key = int(hash(str(value)) % 10**8)
    rng = random.Random(key)
    return rng.choice(options)


def signature_suffix(topic: str, first_frame: bool = False) -> str:
    """Full signature prompt suffix for one scene.

    `topic` (the video title/subject) locks the style for the whole video
    — cohesive per video, varied across the channel, and unlike anything the
    generic stock layer can produce.
    """
    base = SIGNATURE_IDENTITY
    style = pick(topic or "x", SIGNATURE_STYLES)
    tail = _IDENTITY_TAIL
    if first_frame:
        base = (
            "EXTREME FIRST-FRAME HOOK, instantly readable visual action, "
            "tight macro close-up of the exact body phenomenon in motion, "
            "strong contrast, clear subject silhouette, no intro card, "
            "no generic anatomy pose: " + base
        )
    return f"{base}, {style}, {tail}"
