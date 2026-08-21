#!/usr/bin/env python3
"""
SKILLOR — Génération de musiques ORIGINALES (sécurisées pour la monétisation).

The 4 third-party tracks in assets/music/ have UNVERIFIED licenses
(ATTRIBUTION.md) — every one is a Content ID claim risk that can block
monetization. This generates 2 original ambient beds (procedural synthesis,
100% original, zero licensing risk) so the pipeline never depends on
unverified audio.

Usage:
  python scripts/generate_own_music.py
"""

import os
import wave

import numpy as np

SR = 22050
DUR = 120.0
OUT = os.path.join("assets", "music")


def hz(midi: float) -> float:
    return 440.0 * 2.0 ** ((midi - 69.0) / 12.0)


def _write(name: str, sig: np.ndarray) -> str:
    os.makedirs(OUT, exist_ok=True)
    peak = np.abs(sig).max() or 1.0
    pcm = (sig / peak * 0.70 * 32767).astype(np.int16)
    path = os.path.join(OUT, name)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print(f"  ✅ {name} ({os.path.getsize(path) // 1024}KB) — ORIGINAL, monetization-safe")
    return path


def build(name: str, root: int = 36, bpm: float = 55, chords=(36, 39, 43, 46), seed: int = 7) -> str:
    """Dark ambient bed: drone + heartbeat + dissonant pad + noise (original)."""
    rng = np.random.default_rng(seed)
    n = int(SR * DUR)
    t = np.arange(n) / SR
    f = hz(root)

    # drone
    drone = (np.sin(2 * np.pi * f * t) + 0.5 * np.sin(2 * np.pi * 2 * f * t)) * 0.13
    drone *= 0.7 + 0.3 * np.sin(2 * np.pi * t / 18.0)

    # heartbeat
    hb = np.zeros(n)
    period = 60.0 / bpm
    tt = 0.0
    while tt < DUR:
        pos = int(tt * SR)
        if pos + int(0.14 * SR) < n:
            tl = np.arange(int(0.14 * SR)) / SR
            hb[pos : pos + len(tl)] += np.sin(2 * np.pi * 55 * tl) * np.exp(-tl * 16) * 0.08
            dp = pos + int(0.22 * SR)
            if dp + int(0.09 * SR) < n:
                td = np.arange(int(0.09 * SR)) / SR
                hb[dp : dp + len(td)] += np.sin(2 * np.pi * 70 * td) * np.exp(-td * 20) * 0.045
        tt += period

    # dissonant pad (original chord cluster, detuned)
    pad = np.zeros(n)
    for k, m in enumerate(chords):
        fk = hz(m)
        env = np.exp(-((t - (k + 0.5) * DUR / len(chords)) ** 2) / (2 * (DUR / 8) ** 2))
        pad += np.sin(2 * np.pi * fk * 1.001 * t) * env * 0.05
        pad += np.sin(2 * np.pi * fk * 0.999 * t) * env * 0.05

    # sparse dissonant piano-ish plucks (original)
    pluck = np.zeros(n)
    pt = 2.0
    while pt < DUR - 6:
        pos = int(pt * SR)
        note = chords[rng.integers(0, len(chords))] + rng.integers(-2, 3)
        fl = hz(note)
        nl = int(SR * 2.2)
        if pos + nl < n:
            tn = np.arange(nl) / SR
            pluck[pos : pos + nl] += (
                (np.sin(2 * np.pi * fl * tn) + 0.3 * np.sin(2 * np.pi * 2 * fl * tn))
                * np.exp(-tn / 1.1)
                * 0.05
            )
        pt += rng.uniform(4.5, 9.0)

    # noise texture
    noise = rng.standard_normal(n) * 0.004
    k = np.hanning(101)
    k /= k.sum()
    noise = np.convolve(noise, k, mode="same")

    mix = drone + hb + pad + pluck + noise
    # gentle global fade in/out
    fi = int(SR * 1.5)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fi:] *= np.linspace(1, 0, fi)
    return _write(name, mix)


def _genres():
    """2026-08-17: library expanded to 6 original beds (was 2). Each bed is
    procedurally synthesised — 100% original, zero Content ID / licensing
    risk. Variety stops the 'same music every video' reused-content signal
    and lets the editor match bed mood to topic."""
    return [
        ("own_dark_drone.wav", 36, 55, (36, 39, 43, 46), 11),
        ("own_suspense_thrum.wav", 33, 60, (33, 36, 39, 42), 23),
        ("own_mystery_voices.wav", 38, 50, (38, 41, 45, 48), 37),
        ("own_melancholy_dusk.wav", 40, 48, (40, 43, 47, 50), 41),
        ("own_tension_rise.wav", 31, 64, (31, 34, 38, 41), 53),
        ("own_serene_eerie.wav", 43, 44, (43, 46, 50, 53), 59),
    ]


if __name__ == "__main__":
    import sys

    print("🎵 Génération de musiques ORIGINALES (monétisation-safe):")
    # Repo ships .ogg (10x smaller); regenerate then convert:
    #   ffmpeg -i own_dark_drone.wav -c:a libvorbis -q:a 6 own_dark_drone.ogg
    # Backward-compatible: bare run regenerates the original 2 beds; add the
    # --all flag (or set GENERATE_MUSIC_ALL=1) to build the full 6-track library.
    full = ("--all" in sys.argv) or (os.environ.get("GENERATE_MUSIC_ALL", "") == "1")
    library = _genres() if full else _genres()[:2]
    for name, root, bpm, chords, seed in library:
        build(name, root=root, bpm=bpm, chords=chords, seed=seed)
    print(f"Done — {len(library)} original track(s) in assets/music/own_*.wav")
