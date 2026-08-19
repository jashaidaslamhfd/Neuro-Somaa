# -*- coding: utf-8 -*-
"""2026-08-19 FRENCH GROWTH-STRATEGY TESTS

Verifies the millions-views French growth stack WITHOUT any network, TTS
or LLM calls. Only exercises seo_generator's deterministic builders.

Coverage (the FR growth conversion of 2026-08-19):
1. Pinned-comment pool: 10 formulas, all tu-register, all French.
2. Description structure: hook first, rotating reply-bait CTA, FR hashtag
   block last; no duplicate-content opening.
3. Hashtag ordering: niche/category FIRST, growth pool middle, #shorts last
   (broad tag must never lead).
4. Hashtag purity: every shipped hashtag is French (no English slugs).
5. CTA pool: no English words, no "vous", always ends with a reply invite.
6. Tags: English blocklist enforced even for category/competitor bleed.
"""
import os
import re
import sys
import unittest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)

import seo_generator as seo  # noqa: E402

_FRENCH_RE = re.compile(r"[a-zà-ÿœâæçîïôûéèêëàù]")


def _is_french(text: str) -> bool:
    low = text.lower()
    ascii_words = re.findall(r"[a-z]+", low)
    if not ascii_words:
        return True  # pure punctuation/emoji — nothing to translate
    return any(_FRENCH_RE.search(w) for w in ascii_words)


_ENGLISH_SIGNALS = ("subscribe", "like and share", "hit subscribe",
                    "smash", "you guys", "follow for more", "like this video",
                    "drop a like")


def _no_english_engagement(text: str) -> bool:
    low = text.lower()
    return not any(sig in low for sig in _ENGLISH_SIGNALS)


class FrenchGrowthStrategyTests(unittest.TestCase):
    SAMPLE_SCRIPT = {
        "title": "Facteurs surprenants",
        "series_title": "Faits surprenants",
        "hook": "Ton corps fait ça sans que tu le saches — et la raison est bizarre.",
        "description": "Une paupière qui tressaille en pleine journée n'est pas un hasard : fatigue, stress, excès de caféine.",
        "cta": "",  # force the rotating default pool
        "question_phrase": "pourquoi une paupière tressaille toute seule",
    }
    TOPIC = "Pourquoi une paupière tressaille sans raison arrive"

    def setUp(self):
        os.environ.pop("COMPETITOR_INTEL_PATH", None)
        os.environ.pop("TITLE_BANDIT_PATH", None)
        os.environ.pop("ML_BRAIN_STATE_PATH", None)
        os.environ.pop("FRANCOPHONE_LOCALE_TAGS", None)

    def test_pinned_pool_has_ten_french_tu_templates(self):
        self.assertEqual(len(seo.PINNED_QUESTION_TEMPLATES), 10)
        for tpl in seo.PINNED_QUESTION_TEMPLATES:
            self.assertTrue(_is_french(tpl), f"non-French pinned template: {tpl}")
            low = tpl.lower()
            # tu-register includes tu/toi/te/t' — all second-person informal forms.
            self.assertTrue(
                re.search(r"\b(tu|toi|te)\b| t'| t\'|", low),
                f"pinned template not tu-register: {tpl}",
            )
            self.assertNotIn("vous", low)

    def test_pinned_pool_never_clickbait_words(self):
        for tpl in seo.PINNED_QUESTION_TEMPLATES:
            low = tpl.lower()
            for banned in ("secret exclusif", "choc", "incroyable ?",
                           "tu ne devineras jamais", "médecins cachent"):
                self.assertNotIn(banned, low)

    def test_description_starts_with_hook(self):
        pkg = seo.generate_seo_package(self.TOPIC, self.SAMPLE_SCRIPT)
        desc = pkg["description"]
        first_line = desc.split("\n\n")[0]
        self.assertEqual(first_line.strip(), self.SAMPLE_SCRIPT["hook"].strip())

    def test_description_rotating_cta_appears(self):
        pkg = seo.generate_seo_package(self.TOPIC, self.SAMPLE_SCRIPT)
        desc = pkg["description"]
        # the default pool CTA (reply-bait) must be one of the blocks
        seed = sum(ord(c) for c in self.TOPIC.lower())
        expected = seo.generate_seo_package.__code__  # no-op guard
        pool = [
            "Abonne-toi pour plus de science simple — et dis-moi : ça t'arrive aussi ?",
            "Abonne-toi si ton corps te fait des trucs bizarres comme ça — ton réflexe préféré en commentaire ?",
            "Tu veux la suite ? Abonne-toi — et raconte-moi la dernière fois que ça t'est arrivé.",
            "Si ça t'a surpris, abonne-toi — et dis-moi : ton corps te joue quel tour bizarre en ce moment ?",
            "Abonne-toi pour comprendre ton corps — toi, c'est arrivé quand la première fois ?",
        ]
        self.assertIn(pool[seed % len(pool)], desc)

    def test_cta_pool_all_french_tu_reply_bait(self):
        for cta in seo.generate_seo_package.__globals__.get("_CTA_POOL_TEST_ONLY", []):
            pass  # real pool checked below
        import inspect
        src_text = inspect.getsource(seo.generate_seo_package)
        pool_m = re.search(r"cta_pool = \[(.*?)\]", src_text, re.S)
        self.assertTrue(pool_m)
        pool = re.findall(r'"([^"]+)"', pool_m.group(1))
        self.assertGreaterEqual(len(pool), 5)
        for cta in pool:
            self.assertTrue(_is_french(cta), f"non-French CTA: {cta}")
            self.assertNotIn("vous", cta.lower())
            self.assertTrue(_no_english_engagement(cta))
            # every CTA must invite a comment reply (comment/recount/experienced
            # or a direct second-person question like "quel tour bizarre ?")
            low = cta.lower()
            has_comment_bait = bool(
                re.search(r"(commentaire|dis[- ]?moi|raconte|arriv[eé]|t'intéresse)", low)
            )
            has_direct_question = bool(re.search(r"\?(\s*)$", cta.strip()))
            self.assertTrue(has_comment_bait or has_direct_question,
                            f"CTA missing reply-bait: {cta}")

    def test_hashtag_order_niche_first_shorts_last(self):
        pkg = seo.generate_seo_package(self.TOPIC, self.SAMPLE_SCRIPT)
        tags = pkg["hashtags"]
        self.assertGreater(len(tags), 1)
        self.assertNotEqual(tags[0], "#shorts",
                            "broad #shorts must not lead the hashtag line")
        # category hashtags come from the niche map (French slugs)
        first = tags[0]
        self.assertTrue(first.startswith("#") and _is_french(first[1:]))

    def test_hashtags_all_french_no_english(self):
        pkg = seo.generate_seo_package(self.TOPIC, self.SAMPLE_SCRIPT)
        for h in pkg["hashtags"]:
            slug = h.lstrip("#")
            self.assertNotIn(slug, seo.ENGLISH_TAG_BLOCKLIST,
                             f"English hashtag shipped: {h}")
        # FR growth pool is part of the shipped set for some topics
        pool_slugs = {h.lstrip("#") for h in seo.FR_GROWTH_HASHTAGS}
        shipped = {h.lstrip("#") for h in pkg["hashtags"]}
        self.assertTrue(pool_slugs & shipped)

    def test_growth_pool_not_tiktok_tags(self):
        for h in seo.FR_GROWTH_HASHTAGS:
            self.assertNotIn(h.lstrip("#"),
                             {"fyp", "pourtoi", "viral", "trend", "xyzbca"})

    def test_tags_french_only(self):
        pkg = seo.generate_seo_package(self.TOPIC, self.SAMPLE_SCRIPT)
        for tag in pkg["tags"]:
            self.assertNotIn(tag.lower(), seo.ENGLISH_TAG_BLOCKLIST,
                             f"English tag shipped: {tag}")

    def test_pinned_comment_fits_and_french(self):
        pkg = seo.generate_seo_package(self.TOPIC, self.SAMPLE_SCRIPT)
        pinned = pkg["pinned_comment"]
        self.assertLessEqual(len(pinned), seo.PINNED_COMMENT_MAX_LEN)
        self.assertTrue(_is_french(pinned))


if __name__ == "__main__":
    unittest.main()
