# Checklist de lancement France-first

Cette version repart avec un état local vierge (`video_history.json`, `upload_state.json` et historique de médias) : les anciennes vidéos anglaises ne doivent pas servir de référence à la nouvelle ligne éditoriale française.

Avant le premier upload :

1. Si vous réutilisez **la même chaîne YouTube**, passez les anciennes vidéos non francophones en **non répertorié** ou créez idéalement une nouvelle chaîne française. Le code ne peut pas modifier ni supprimer des vidéos déjà publiées à votre place.
2. Dans YouTube Studio, définissez la langue par défaut de la chaîne et des vidéos sur **Français**, ainsi que le pays de résidence approprié.
3. Vérifiez que le nom, la bannière, l'avatar, la section « À propos » et les playlists sont français. Ce sont des réglages YouTube Studio, pas des fichiers du dépôt.
4. Ajoutez les secrets GitHub. Pour les tout premiers uploads, passez `YT_PRIVACY_STATUS` à `private` **dans `.github/workflows/main.yml`** (le workflow de production est réglé sur `public` + publication programmée, donc il publie sans relecture). Repassez en `public` une fois la qualité validée.
5. Faites un essai privé : prononciation de la voix, lisibilité des sous-titres, exactitude scientifique, droits des images/musiques, titre, miniature et description.
6. N'analysez les performances qu'après assez d'impressions ; ne modifiez pas toute la stratégie après une seule vidéo.

La géolocalisation, la langue et les métadonnées offrent des signaux cohérents à YouTube ; elles ne garantissent jamais une recommandation. La diffusion est décidée par les réactions réelles des spectateurs.
