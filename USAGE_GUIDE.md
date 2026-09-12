# Guide d'utilisation — Chaîne France

1. Copiez `env.example` vers `.env` et renseignez les clés API.
2. Conservez `TREND_REGION=FR`, `YOUTUBE_REGION_CODE=FR`, `CHANNEL_LANGUAGE=fr-FR` et `TTS_ENGINE=kokoro`.
3. Exécutez `python src/main.py` ou `python src/main.py --topic "Pourquoi le bâillement est contagieux"`.
4. Vérifiez l'upload privé dans YouTube Studio avant publication.

Le catalogue `data/body_glitch_topics.json` contient 500 sujets en français. Le workflow GitHub Actions régénère ce catalogue et utilise le fuseau `Europe/Paris`.

Ne présentez jamais une vidéo éducative comme un diagnostic ou un traitement. Ne publiez pas de contenu répétitif, de contenu réutilisé sans transformation, ni d'automatisation d'engagement.
