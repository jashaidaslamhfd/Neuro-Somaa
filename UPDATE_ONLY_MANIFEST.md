# Livraison SKILLOR France-first

Les fichiers modifiés dans cette livraison remplacent les fichiers correspondants du dépôt. Après contrôle :

```bash
git add .
git commit -m "feat: convert SKILLOR to France-first channel"
git push origin main
```

Secrets requis pour la génération : `GROQ_API_KEY`. L'upload YouTube nécessite en plus `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` et `REFRESH_TOKEN`.
