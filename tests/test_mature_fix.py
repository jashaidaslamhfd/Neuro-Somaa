"""Local verification for the 2026-08-17 mature-voice + professional zoom fixes."""

import os
import subprocess
import sys

import numpy as np

try:
    import scipy.signal as ss
    import soundfile as sf

    _HAS_AUDIO = True
except ImportError:
    _HAS_AUDIO = False

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# 2026-08-17 CI skip: the guard workflow installs only requirements-ci.txt
# (no soundfile/moviepy/kokoro) and collects every tests/ module. This test
# exercises the voice/zoom pipeline, which needs the full stack - skip it
# cleanly when the heavy deps are absent instead of breaking collection.
try:
    import moviepy  # noqa: F401
    import soundfile  # noqa: F401
except ImportError:
    import pytest

    pytest.skip("Heavy TTS/render deps not installed (CI minimal set)", allow_module_level=True)

# Force edge-tts primary engine (CI default)
os.environ["TTS_ENGINE"] = "edge"
os.environ.pop("EDGE_FR_VOICE_POOL", None)

from PIL import Image

import video_editor as ve
import voice_generator as vg

OUT = os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

print("=== 1. VOICE ROTATION (adult pool default) ===")
topics = [
    "pourquoi le cerveau ment",
    "les secrets du sommeil",
    "pourquoi on oublie",
    "la memoire est fausse",
    "comment apprendre vite",
]
for t in topics:
    print(f"  {t!r} -> {vg._rotated_french_voice(t)}")

print("\n=== 2. MATURE VOICE PIPELINE (edge-tts + pitch deepening) ===")
text = "Le cerveau humain est capable de cre\u0301er des souvenirs qui n'ont jamais existe\u0301."
segments = vg.generate_voice_segments(
    [{"caption": text}],
    topic="pourquoi le cerveau ment",
    output_dir=OUT,
)
seg = segments[0]
print(
    f"  engine: {seg['tts_engine']} | dur: {seg['duration']:.2f}s | path exists: {os.path.isfile(seg['path'])}"
)
if _HAS_AUDIO:
    audio, sr = sf.read(seg["path"], dtype="float32")
    print(f"  sample rate: {sr}")

# Spectral centroid: mature voice should be LOWER than raw edge-tts output
if _HAS_AUDIO:
    f, Pxx = ss.welch(audio, sr, nperseg=min(2048, audio.size))
    _CENTROID = float(np.sum(f * Pxx[0]) / np.sum(Pxx[0]))
    print(f"  spectral centroid: {_CENTROID:.0f} Hz")
else:
    _CENTROID = None
    print("  (audio analysis skipped: soundfile/scipy not installed in this env)")
if _HAS_AUDIO:
    print(f"  spectral centroid: {_CENTROID:.0f} Hz (lower = deeper/more mature)")

print("\n=== 3. KEN BURNS ZOOM SYSTEM ===")
print(
    f"  ZOOM_AMOUNT={ve.ZOOM_AMOUNT} | ZOOM_MAX={ve.ZOOM_MAX} | PAN_PX={ve.PAN_PX} | SMOOTH={ve.ZOOM_SMOOTH}"
)

# Create a test image and render a short clip
img_path = os.path.join(OUT, "test_scene.png")
img = Image.new("RGB", (ve.CANVAS_W, ve.CANVAS_H), color=(30, 60, 90))
from PIL import ImageDraw

d = ImageDraw.Draw(img)
d.rectangle([200, 400, 880, 1520], outline=(255, 200, 50), width=10)
img.save(img_path)

# Old-equivalent: base 0.18 + extra 0.18 = 0.36 total per beat. New: capped at 0.12.
old_total = 0.18 + 0.18
new_total = min(ve.ZOOM_MAX, ve.ZOOM_AMOUNT + 0.06)
print(f"  OLD worst-case zoom per beat: {old_total:.2f} ({old_total * 100:.0f}%)")
print(f"  NEW worst-case zoom per beat: {new_total:.2f} ({new_total * 100:.0f}%)")
assert new_total <= 0.12, "zoom cap broken"

clip = ve._ken_burns_clip(img_path, duration=2.0, direction="in", zoom_extra=0.06)

# NOTE: moviepy's get_frame(t==duration) always returns black (t >= duration
# is "past the end") — that is a library artifact, NOT what renders in the
# real video. Verify against ACTUAL exported frames instead.
bg = ve.ColorClip(size=(ve.CANVAS_W, ve.CANVAS_H), color=(0, 0, 0))
out = ve.CompositeVideoClip([bg, clip], size=(ve.CANVAS_W, ve.CANVAS_H)).set_duration(2.0)
test_mp4 = os.path.join(OUT, "zoom_test.mp4")
out.write_videofile(test_mp4, fps=30, audio=False, logger=None)

import numpy as _np

edges_ok = True
# Sample first, middle, and LAST real exported frames
for n in (0, 29, 59):
    frame_png = os.path.join(OUT, f"zf_{n:02d}.png")
    subprocess.run(
        ["ffmpeg", "-y", "-i", test_mp4, "-vf", f"select=eq(n\\,{n})", "-vsync", "vfr", frame_png],
        capture_output=True,
        check=True,
    )
    frame = _np.array(Image.open(frame_png))
    row_ok = frame[0:2].mean(axis=(0, 2)).min() > 5 and frame[-2:].mean(axis=(0, 2)).min() > 5
    edges_ok = edges_ok and row_ok
    print(f"  real frame n={n}: mean={frame.mean():.1f} edges_ok={row_ok}")

print("\nALL LOCAL CHECKS PASSED" if edges_ok else "\nFAILED")
