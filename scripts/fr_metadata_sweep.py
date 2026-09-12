#!/usr/bin/env python3
"""Balayage FR — répare les métadonnées de TOUTES les vidéos en ligne.

Contrairement à scripts/video_repair.py (liste d'ID figée pour l'audit du
2026-07-25), ce script SCANNE la chaîne et décide vidéo par vidéo. Il peut
donc être relancé après chaque audit sans être réécrit.

Défauts corrigés (mesurés sur la chaîne le 2026-07-26) :

1. TAGS ANGLAIS sur une chaîne française — 11 vidéos en ligne portaient
   ['anatomy', 'humanbody', 'bodyfacts', 'yourbody', 'physiology', ...].
   Sur 9 d'entre elles l'anglais écrasait le français 10 contre 4. Le
   classifieur YouTube reçoit alors « vidéo anglaise » alors que l'audio,
   les sous-titres et le titre sont français : le signal d'audience se
   divise exactement là où la chaîne en a besoin.

2. TAGS DE GABARIT — « faut », « qu'il », « comprendre », « explique »,
   « semble », « moment »… Ce sont les mots de structure des templates de
   titres, transformés en tags par _keywords(). Personne ne les cherche et
   ils diluent les 3-4 tags réellement descriptifs.

3. DESCRIPTIONS EN DOUBLE — la même phrase répétée 2 à 3 fois avant la
   moindre information, puis le bloc hook+CTA+hashtags dupliqué à
   l'identique. Signal de contenu dupliqué, et les deux seules lignes
   visibles dans le feed sont gâchées.

Sécurité :
  - DRY-RUN par défaut ; --apply pour écrire.
  - Ne touche JAMAIS aux titres (les vidéos à 1 000+ vues ont leur
    momentum ; on ne réécrit pas un titre qui marche).
  - Ne supprime rien.
  - YouTube efface les champs omis lors d'un update : le payload renvoie
    donc titre / categoryId / langues à l'identique.

Env requis : GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / REFRESH_TOKEN
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fr-sweep")

API = "https://www.googleapis.com/youtube/v3"

# --- Tags anglais à supprimer d'une chaîne francophone ---------------------
ENGLISH_TAGS = {
    "anatomy",
    "physiology",
    "humanbody",
    "human body",
    "yourbody",
    "your body",
    "bodyfacts",
    "body facts",
    "bodyparts",
    "body parts",
    "bodymystery",
    "bodyawareness",
    "humanfacts",
    "humananatomy",
    "human anatomy",
    "brainfacts",
    "brain facts",
    "sciencefacts",
    "science facts",
    "didyouknow",
    "facts",
    "body",
    "brain",
    "health",
    "mindblown",
    "amazingfacts",
    "shortsfeed",
    "viral",
    "fyp",
    "bodyscience",
    "body science",
    "bodyhacks",
    "healthfacts",
}

# Préfixes anglais : attrape les variantes composées non listées
# ("bodysignals", "brainpower", "humanbiology"…) sans toucher au français.
ENGLISH_PREFIXES = ("body", "human", "brain", "health", "science f", "your body")

# --- Mots de gabarit : jamais des mots-clés de recherche -------------------
TEMPLATE_TAGS = {
    "faut",
    "qu'il",
    "quil",
    "qu",
    "comprendre",
    "explique",
    "expliquer",
    "derrière",
    "derriere",
    "passe",
    "semble",
    "sembler",
    "avant",
    "après",
    "apres",
    "moment",
    "important",
    "vraiment",
    "toujours",
    "jamais",
    "chaque",
    "aussi",
    "très",
    "bien",
    "faire",
    "fait",
    "dit",
    "dire",
    "voici",
    "vraie",
    "vrai",
    "raison",
    "chose",
    "choses",
    "tout",
    "tous",
    "autre",
    "autres",
    "alors",
    "donc",
    "mais",
    "lors",
    "lorsque",
    "parfois",
    "souvent",
    "votre",
    "vous",
    "notre",
    "ton",
    "ta",
    "tes",
    "cela",
    "quand",
    "pourquoi",
    "comment",
    "bougeant",
    "entendus",
    "mâchant",
    "repère",
    "propre",
    "science",
    "d'une",
    "dune",
    "d'un",
    "plus",
    "vite",
    "cette",
    "leur",
    "sans",
    "dans",
    "avec",
    "pour",
    "étrangement",
    "devient",
}


def _is_english_tag(tag: str) -> bool:
    """Un tag anglais compressé ('bodysignals') n'a pas d'accent, pas
    d'espace, et commence par une racine anglaise connue."""
    normalized = tag.lower().strip()
    if normalized in ENGLISH_TAGS:
        return True
    if any(ch in normalized for ch in "àâäéèêëïîôöùûüÿçœæ"):
        return False  # accent => français
    return normalized.startswith(ENGLISH_PREFIXES)


# Socle FR appliqué à toutes les vidéos de la série.
BASE_TAGS = [
    "shorts",
    "corps humain",
    "science",
    "français",
    "faits étonnants",
    "curiosité",
    "anatomie",
    "vulgarisation",
]

MAX_TAGS = 14


def _token() -> str:
    data = urllib.parse.urlencode(
        {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "refresh_token": os.environ["REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }
    ).encode()
    with urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=30
    ) as response:
        return json.load(response)["access_token"]


def _req(method: str, url: str, token: str, payload: dict | None = None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    if body:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        log.error(
            "%s %s -> HTTP %s: %s",
            method,
            url.split("?")[0],
            exc.code,
            exc.read().decode("utf-8", "replace")[:300],
        )
        raise


def _all_video_ids(token: str) -> list[str]:
    channel = _req("GET", f"{API}/channels?part=contentDetails&mine=true", token)
    uploads = channel["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while True:
        url = f"{API}/playlistItems?part=contentDetails&playlistId={uploads}&maxResults=50"
        if page:
            url += f"&pageToken={page}"
        data = _req("GET", url, token)
        ids += [i["contentDetails"]["videoId"] for i in data.get("items", [])]
        page = data.get("nextPageToken")
        if not page:
            return ids


def _fetch(token: str, ids: list[str]) -> list[dict]:
    out = []
    for i in range(0, len(ids), 50):
        chunk = ",".join(ids[i : i + 50])
        data = _req("GET", f"{API}/videos?part=snippet,statistics&id={chunk}", token)
        out += data.get("items", [])
    return out


def _topic_words(title: str) -> list[str]:
    """Mots-clés réels extraits du titre (sans le gabarit)."""
    words = re.findall(r"[a-zà-ÿœæ]+(?:'[a-zà-ÿœæ]+)?", title.lower())
    keep = []
    for word in words:
        if (
            len(word) > 3
            and word not in TEMPLATE_TAGS
            and word not in ENGLISH_TAGS
            and word not in keep
        ):
            keep.append(word)
    return keep[:6]


def clean_tags(title: str, current: list[str]) -> tuple[list[str], dict]:
    """Retourne (nouveaux_tags, rapport). Conserve les bons tags FR existants."""
    current = current or []
    removed_en = [t for t in current if _is_english_tag(t)]
    removed_tpl = [t for t in current if not _is_english_tag(t) and t.lower().strip() in TEMPLATE_TAGS]
    kept = [
        t
        for t in current
        if not _is_english_tag(t) and t.lower().strip() not in TEMPLATE_TAGS and len(t.strip()) > 2
    ]
    # Ordre stable et prioritaire : mots-clés du sujet d'abord (ce que les
    # gens tapent réellement), puis les bons tags déjà en place, puis le
    # socle de marque. Sans cet ordre fixe, relancer le script permutait les
    # tags et la troncature à MAX_TAGS en faisait tomber un différent à
    # chaque passage — donc un update YouTube inutile à chaque exécution.
    merged = list(dict.fromkeys(_topic_words(title) + kept + BASE_TAGS))[:MAX_TAGS]
    return merged, {"removed_english": removed_en, "removed_template": removed_tpl}


def clean_description(description: str) -> tuple[str, dict]:
    """Supprime les paragraphes répétés et les phrases d'ouverture dupliquées."""
    original = description or ""
    blocks = [b.strip() for b in original.split("\n\n") if b.strip()]

    deduped, seen = [], set()
    for block in blocks:
        key = re.sub(r"[^a-zà-ÿœ0-9 ]", "", block.lower()).strip()
        if key and key in seen:
            continue
        seen.add(key)
        deduped.append(block)

    # Première phrase répétée à l'intérieur du premier paragraphe.
    if deduped:
        sentences = re.split(r"(?<=[.!?])\s+", deduped[0])
        if len(sentences) > 1:
            out, seen_s = [], set()
            for sentence in sentences:
                key = re.sub(r"[^a-zà-ÿœ0-9 ]", "", sentence.lower()).strip()
                if key and key in seen_s:
                    continue
                seen_s.add(key)
                out.append(sentence)
            deduped[0] = " ".join(out)

    # Bloc de hashtags : n'en garder qu'UN seul, fusionné et dédupliqué.
    # Les descriptions en ligne finissent par plusieurs lignes de hashtags
    # ("#shorts #corpshumain …" puis "#corps #mâchoire #craque"), qui ne sont
    # pas des paragraphes identiques et survivaient donc au filtre ci-dessus.
    def _is_hashtag_block(text: str) -> bool:
        tokens = text.split()
        return bool(tokens) and all(tok.startswith("#") for tok in tokens)

    tags_seen, merged_hashtags, body = set(), [], []
    for block in deduped:
        if _is_hashtag_block(block):
            for tag in block.split():
                if tag.lower() not in tags_seen:
                    tags_seen.add(tag.lower())
                    merged_hashtags.append(tag)
        else:
            body.append(block)

    hashtags_removed = sum(1 for b in deduped if _is_hashtag_block(b))
    # Drop junk hashtags from the merged line too. The published
    # descriptions carry template scaffolding as hashtags — "#quil #faut
    # #comprendre", "#explique", "#passe", "#semble", "#derrière" — plus the
    # far-too-broad "#science" (19 of them across 8 videos on 2026-07-27).
    # Merging duplicates alone left all of them in place.
    HASHTAG_JUNK = TEMPLATE_TAGS | {
        "science",
        "sciences",
        "corps",
        "chose",
        "choses",
        "effet",
        "cause",
        "raison",
    }
    kept_hashtags = [
        tag
        for tag in merged_hashtags
        if len(tag.lstrip("#")) > 3
        and tag.lstrip("#").lower() not in HASHTAG_JUNK
        and not _is_english_tag(tag.lstrip("#"))
    ]
    final_blocks = body + ([" ".join(kept_hashtags[:15])] if kept_hashtags else [])

    cleaned = "\n\n".join(final_blocks).strip()[:4900]
    return cleaned, {
        "paragraphs_removed": len(blocks) - len(final_blocks),
        "hashtag_blocks_merged": max(0, hashtags_removed - 1),
        "chars_saved": len(original) - len(cleaned),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="écrire sur YouTube")
    parser.add_argument("--limit", type=int, default=0, help="0 = toutes")
    args = parser.parse_args()

    token = _token()
    ids = _all_video_ids(token)
    videos = _fetch(token, ids)
    if args.limit:
        videos = videos[: args.limit]
    log.info("%d vidéos scannées (mode %s)", len(videos), "APPLY" if args.apply else "DRY-RUN")

    changed = 0
    report = []
    for video in videos:
        vid = video["id"]
        snippet = video["snippet"]
        title = snippet.get("title", "")
        views = int(video.get("statistics", {}).get("viewCount", 0) or 0)

        new_tags, tag_report = clean_tags(title, snippet.get("tags"))
        new_desc, desc_report = clean_description(snippet.get("description", ""))

        # Comparaison insensible à l'ordre : un simple réarrangement des mêmes
        # tags ne justifie pas un update (chaque écriture coûte 50 unités de
        # quota et republie la vidéo pour rien).
        current_tags = snippet.get("tags") or []
        tags_changed = {t.lower() for t in new_tags} != {t.lower() for t in current_tags}
        desc_changed = new_desc != (snippet.get("description") or "").strip()
        if not (tags_changed or desc_changed):
            continue

        changed += 1
        entry = {
            "video_id": vid,
            "title": title,
            "views": views,
            "removed_english_tags": tag_report["removed_english"],
            "removed_template_tags": tag_report["removed_template"],
            "paragraphs_removed": desc_report["paragraphs_removed"],
            "chars_saved": desc_report["chars_saved"],
        }
        report.append(entry)

        log.info("[%s] %s (%d vues)", vid, title[:52], views)
        if tag_report["removed_english"]:
            log.info("    - tags EN supprimés : %s", tag_report["removed_english"])
        if tag_report["removed_template"]:
            log.info("    - tags gabarit supprimés : %s", tag_report["removed_template"])
        if desc_report["paragraphs_removed"]:
            log.info(
                "    - %d paragraphe(s) dupliqué(s) retirés (%d caractères)",
                desc_report["paragraphs_removed"],
                desc_report["chars_saved"],
            )
        log.info("    → tags : %s", new_tags)

        if args.apply:
            payload = {
                "id": vid,
                "snippet": {
                    "title": title,  # inchangé volontairement
                    "description": new_desc,
                    "tags": new_tags,
                    "categoryId": snippet.get("categoryId", "28"),
                    "defaultLanguage": snippet.get("defaultLanguage", "fr"),
                    "defaultAudioLanguage": snippet.get("defaultAudioLanguage", "fr"),
                },
            }
            _req("PUT", f"{API}/videos?part=snippet", token, payload)
            log.info("    ✅ mis à jour")
            time.sleep(1)

    os.makedirs("output", exist_ok=True)
    with open("output/fr_metadata_sweep.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "mode": "apply" if args.apply else "dry-run",
                "scanned": len(videos),
                "changed": changed,
                "videos": report,
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    log.info(
        "Terminé : %d/%d vidéos %s",
        changed,
        len(videos),
        "mises à jour" if args.apply else "à corriger (dry-run)",
    )
    if not args.apply and changed:
        log.info("Relancer avec --apply pour écrire les corrections.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
