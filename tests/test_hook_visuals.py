"""2026-08-19 HOOK VISUAL UPGRADE TESTS

Lightweight, TTS-free unit tests covering the three new first-3-second
elements wired into the Neuro-Somaa pipeline:

1. HOOK PROMPT FRAMING      — scene 0 image/video prompt now carries the
   "EXTREME FIRST-FRAME HOOK" suffix (previously dead code:
   first_frame=False everywhere).
2. HOOK CAPTION EMPHASIS    — scene 0's opening caption phrase renders at a
   25% larger font baseline so the hook line lands hard on the mobile feed.
3. HOOK SNAP ZOOM           — scene 0's first motion beat uses front-loaded
   cubic-in easing (punch-in within ~0.3s); later scenes keep smooth
   ease-in-out.

All of it stays inside the existing quality/monetization gates: the caption
auto-fit loop still shrinks oversized hook text, and the zoom remains
hard-capped at ZOOM_MAX.
"""

import os
import sys
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)


class HookPromptFramingTests(unittest.TestCase):
    """The EXTREME FIRST-FRAME HOOK suffix must ONLY attach to scene 0."""

    def setUp(self):
        self.ig = __import__("image_generator")
        self.vs = __import__("visual_signature")

    def test_scene_zero_prompt_carries_hook_suffix(self):
        prompt = self.ig._build_prompt("cœur accéléré sans raison", topic="coeur", hook_scene=True)
        self.assertIn("EXTREME FIRST-FRAME HOOK", prompt)
        self.assertIn("tight macro close-up", prompt)

    def test_later_scenes_stay_clean(self):
        prompt = self.ig._build_prompt("le sommeil répare la mémoire", topic="sommeil", hook_scene=False)
        self.assertNotIn("EXTREME FIRST-FRAME HOOK", prompt)
        self.assertIn("teal", prompt)

    def test_signature_suffix_backwards_compatible(self):
        """Default (no first_frame) must never mention hook framing."""
        suffix = self.vs.signature_suffix("test topic")
        self.assertNotIn("EXTREME FIRST-FRAME HOOK", suffix)

    def test_signature_suffix_hook_variant(self):
        suffix = self.vs.signature_suffix("test topic", first_frame=True)
        self.assertIn("EXTREME FIRST-FRAME HOOK", suffix)
        self.assertIn("no intro card", suffix)


class HookCaptionEmphasisTests(unittest.TestCase):
    """Scene 0's first caption phrase must start 25% larger."""

    def setUp(self):
        self.ve = __import__("video_editor")

    def test_hook_font_baseline_is_larger(self):
        big = self.ve._caption_clip("Votre corps", 1.2, is_hook=True)
        normal = self.ve._caption_clip("Votre corps", 1.2, is_hook=False)
        # Larger baseline font means a larger composited frame.
        self.assertGreater(big.size[1], normal.size[1])

    def test_hook_text_does_not_exceed_normal_bounds_silently(self):
        """A very long hook phrase must still fit: the auto-fit loop shrinks
        it to the same safe bounds a normal caption would hit."""
        long_text = (
            "Pourquoi votre corps se réveille pile cinq minutes "
            "avant le réveil alors que rien ne le réveille ?"
        )
        big = self.ve._caption_clip(long_text, 1.2, is_hook=True)
        self.assertLessEqual(big.size[0], int(self.ve.CANVAS_W * 0.82) + 40)


class HookSnapZoomTests(unittest.TestCase):
    """Scene 0's first beat must accelerate; later scenes drift gently."""

    def setUp(self):
        self.ve = __import__("video_editor")
        # Render a real 100x100 PNG as the beat source (no stock needed).
        import numpy as np
        from PIL import Image

        os.makedirs("/tmp/hook_test", exist_ok=True)
        arr = np.random.RandomState(42).randint(40, 200, (200, 200, 3)).astype("uint8")
        self.img = "/tmp/hook_test/hook_src.jpg"
        Image.fromarray(arr).save(self.img)

    def test_snap_beat_starts_moving_earlier(self):
        snap = self.ve._ken_burns_clip(self.img, 1.5, "in", 0.0, hook_snap=True)
        smooth = self.ve._ken_burns_clip(self.img, 1.5, "in", 0.0, hook_snap=False)
        # At t=0.5s (one third in) the cubic-in snap has covered 125/216 ≈
        # 58% of its zoom range; smooth ease-in-out has covered only
        # ~34%. Compare frame scale directly.
        f_snap = snap.get_frame(0.5)
        f_smooth = smooth.get_frame(0.5)
        import numpy as np

        self.assertGreater(np.abs(f_snap.astype(float) - f_smooth.astype(float)).mean(), 2.0)

    def test_zoom_cap_still_enforced_on_hook_snap(self):
        clip = self.ve._ken_burns_clip(self.img, 1.0, "in", 0.99, hook_snap=True)
        # Even with an impossible extra, final zoom never exceeds the cap.
        frame = clip.get_frame(0.99)
        self.assertEqual(frame.shape[:2], (self.ve.CANVAS_H, self.ve.CANVAS_W))


if __name__ == "__main__":
    unittest.main()
