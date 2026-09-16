from __future__ import annotations

import os


def get_youtube():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    credentials = Credentials(
        None,
        refresh_token=os.environ["REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)

# Mapping of boring/repetitive titles to high-CTR viral hooks for recent videos
VIRAL_UPGRADES = {
    "gDbVsTzTPCw": {
        "title": "Ton corps réagit comme ça après la chaleur ? 🧠",
        "tags": ["cerveau", "sommeil", "fatigue", "santé", "corps humain", "chaleur", "shorts français", "science", "dopamine"]
    },
    "ARkMujULlT0": {
        "title": "Le secret du sommeil profond contre le stress 🤯",
        "tags": ["sommeil", "stress", "cerveau", "santé mentale", "dopamine", "corps humain", "shorts français", "science"]
    },
    "NVhIl1uaXkc": {
        "title": "Ce secret sur la mémoire va te choquer ! 🧠",
        "tags": ["cerveau", "mémoire", "science", "curiosité", "corps humain", "shorts français", "france"]
    },
    "Vqqpn02WANw": {
        "title": "Ne regarde JAMAIS ton écran comme ça...",
        "tags": ["téléphone", "écran", "sommeil", "yeux", "cerveau", "shorts français", "science", "santé"]
    },
    "BYaH1bgUowY": {
        "title": "Ton cerveau reste éveillé quand tu dors ? 🧠",
        "tags": ["cerveau", "sommeil", "rêves", "inconscient", "shorts français", "science", "mystère"]
    }
}

def optimize_all():
    yt = get_youtube()
    for vid, meta in VIRAL_UPGRADES.items():
        try:
            res = yt.videos().list(part="snippet,status", id=vid).execute()
            items = res.get("items", [])
            if not items:
                continue
            item = items[0]
            snippet = item["snippet"]
            
            # Apply punchy viral title
            old_title = snippet["title"]
            snippet["title"] = meta["title"]
            snippet["tags"] = meta["tags"]
            
            # Ensure description contains high-volume hashtags
            if "#shorts" not in snippet.get("description", ""):
                snippet["description"] = str(snippet.get("description") or "") + "\n\n#shorts #cerveau #science #france"

            yt.videos().update(
                part="snippet",
                body={
                    "id": vid,
                    "snippet": snippet
                }
            ).execute()
            print(f"[{vid}] Updated: \"{old_title}\" -> \"{meta['title']}\"")
        except Exception as e:
            print(f"[{vid}] Error: {e}")

if __name__ == "__main__":
    optimize_all()
