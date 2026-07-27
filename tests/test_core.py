"""Tests offline de la configuration éditoriale France-first."""
import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from seo_generator import generate_seo_package
from trend_fetcher import get_body_glitch_topics, _is_relevant
from shorts_enhancer import score_hook
class FranceChannelTests(unittest.TestCase):
    def test_catalogue_is_french_and_complete(self):
        records=get_body_glitch_topics()
        self.assertGreaterEqual(len(records),500)
        self.assertEqual(records[0]['series_title'],'Paupière qui saute')
        self.assertEqual(records[0]['source'],'body_glitch_series_fr')
        self.assertTrue(all(x['pillar']=='reflexes_du_corps' for x in records))
    def test_french_relevance_filter(self):
        self.assertTrue(_is_relevant('Pourquoi le cerveau a besoin de sommeil'))
        self.assertFalse(_is_relevant('Résultat du match de football'))
    def test_seo_is_french(self):
        package=generate_seo_package('Pourquoi une paupière tressaille',{'title':'Pourquoi la paupière tressaille','thumbnail_text':'ŒIL QUI SAUTE','hook':'Pourquoi votre paupière saute parfois','description':'Un réflexe musculaire courant peut faire tressauter une paupière.','cta':'Abonnez-vous pour plus de science simple.'})
        # Hashtags must be French and Shorts-tagged. '#science' is no longer
        # asserted: it was the lead category hashtag and is far too broad to
        # help a Short, so it was replaced with #culturegenerale /
        # #saviezvous / #corpshumain (see CATEGORY_HASHTAGS).
        self.assertIn('#shorts',package['hashtags'])
        self.assertTrue(any(h in package['hashtags'] for h in
                            ('#culturegenerale','#saviezvous','#corpshumain',
                             '#anatomie','#cerveau','#neurosciences')),
                        package['hashtags'])
        # No template scaffolding may reach the hashtag line.
        for junk in ('#quil','#faut','#comprendre','#semble','#explique','#passe'):
            self.assertNotIn(junk,[h.lower() for h in package['hashtags']])
        self.assertIn('français',package['tags'])
        # Pinned comment is now topic-specific (varied per video) instead of
        # one hardcoded string reused on every single upload - identical
        # pinned comments across a channel's uploads can look templated/spam
        # to both viewers and YouTube's systems.
        self.assertTrue(package['pinned_comment'])
        self.assertLessEqual(len(package['pinned_comment']), 200)
        self.assertEqual(package['chosen_title'], package['title'])
        # seo_score is now computed from real signals, not hardcoded to 85.
        self.assertIn('seo_score', package)
        self.assertIn('scores', package['seo_score'])
        self.assertIn('overall_seo_score', package['seo_score']['scores'])
        self.assertTrue(
            0 <= package['seo_score']['scores']['overall_seo_score'] <= 100,
            "overall_seo_score should be a computed 0-100 value",
        )
        # The chosen title should be the real SEO-rich angle, not just a
        # 2-3 word branded label - this was the main bug being fixed.
        self.assertGreater(len(package['chosen_title'].split()), 3)
    def test_french_hook_receives_a_score(self):
        self.assertGreaterEqual(score_hook('Pourquoi votre cerveau remarque votre prénom')['score'],50)

    def test_catalogue_angles_are_grammatical_french(self):
        import re
        from french_quality_gate import _DANGLING_CAPTION_END
        records=get_body_glitch_topics()
        angles=[r['angle'] for r in records]
        self.assertEqual(len(set(angles)),len(angles),'every topic must be unique')
        for angle in angles:
            self.assertNotRegex(angle, r'\s{2,}', 'no double spaces')
            self.assertNotRegex(angle, r'[.!?…]\s+(et|ou|ni)\b', 'no broken continuation')
            last=re.sub(r'[^a-zà-ÿœ]','',angle.split()[-1].lower())
            self.assertNotIn(last,_DANGLING_CAPTION_END,f'dangling ending: {angle!r}')
        # The ungrammatical template that shipped the broken public title
        # ("Pourquoi le cerveau remarque entendre son cœur battre la") must
        # never come back in any form.
        self.assertFalse(any('remarque entendre' in a for a in angles))
        self.assertFalse(any(a.startswith('Pourquoi le cerveau remarque') for a in angles))

    def test_long_angle_falls_back_to_branded_series_title(self):
        from seo_generator import _truncate_title, _DANGLING_ENDINGS
        # Historical incident: cutting a long angle produced a visible
        # truncated-fragment title on the channel. The default pick must now
        # be the short branded series title instead.
        package=generate_seo_package(
            'Pourquoi le cerveau remarque entendre son cœur battre la nuit',
            {'series_title':'Battements entendus','title':'Battements entendus',
             'hook':'On entend son cœur la nuit','description':'Le calme laisse mieux entendre le corps.',
             'cta':'Abonnez-vous.'})
        self.assertEqual(package['chosen_title'],'Battements entendus')
        # Truncator by itself must never leave a dangling connector at the end.
        for sample in ('Ce qu\u2019il faut comprendre sur le visage qui rougit par gêne',
                       'Pourquoi le cerveau remarque entendre son cœur battre la nuit'):
            cut=_truncate_title(sample)
            import re as _re
            last=_re.sub(r'[^a-zà-ÿœ]','',cut.split()[-1].lower())
            self.assertNotIn(last,_DANGLING_ENDINGS,cut)

    def test_gate_blocks_broken_french_voiceover(self):
        from french_quality_gate import validate_publication_quality
        broken={'title':'Battements entendus','hook':'On entend son cœur la nuit',
                'cta':'Abonnez-vous pour plus de science.','description':'Le calme aide à entendre son corps.',
                'topic':'les battements de cœur entendus la nuit',
                'scenes':[{'caption':c,'visual':'un corps humain dans la nuit'} for c in
                    ['La nuit, vous vous endormez tranquillement, mais votre cerveau.',
                     'Et écoute les sons de votre corps, comme votre respiration et votre cœur.',
                     'Le cœur bat régulièrement, même quand vous dormez, car il doit toujours fonctionner.',
                     'Le cerveau utilise les nerfs pour écouter les battements du cœur de votre corps.',
                     'Ces sons internes deviennent audibles quand tout le reste devient très calme.',
                     'Cela est habituel et ne signale pas un problème dans votre corps la nuit.',
                     'Un rythme calme et régulier est simplement le signe de votre repos du soir.',
                     'Voilà pourquoi vous entendez parfois votre cœur battre pendant la nuit.']]}
        approved,report=validate_publication_quality(broken)
        self.assertFalse(approved)
        self.assertTrue(any('continuation' in i or 'conjunction' in i for i in report['issues']))

    def test_gate_approves_clean_french_script(self):
        from french_quality_gate import validate_publication_quality
        clean={'title':'Battements entendus','hook':'Vous entendez votre cœur la nuit ?',
               'cta':'Abonnez-vous pour plus de science simple.','description':'Le calme laisse mieux entendre le corps.',
               'topic':'les battements de cœur entendus la nuit',
               'scenes':[{'caption':c,'visual':'un coeur humain dans la nuit'} for c in
                    ['Vous entendez parfois votre cœur battre la nuit.',
                     'Pourquoi ce son devient-il si présent quand tout dort ?',
                     'Beaucoup croient que le corps se met au silence complet la nuit.',
                     'En réalité, le cœur bat régulièrement, même pendant votre sommeil.',
                     'Le cerveau continue de recevoir ces signaux nerveux de votre corps.',
                     'Sans bruit extérieur, ces sons internes semblent simplement plus forts.',
                     'Un rythme calme et régulier est habituel pendant le repos de la nuit.',
                     'Voilà pourquoi votre cœur semble battre plus fort la nuit.']]}
        approved,report=validate_publication_quality(clean)
        self.assertTrue(approved,report['issues'])
if __name__=='__main__': unittest.main()
        
