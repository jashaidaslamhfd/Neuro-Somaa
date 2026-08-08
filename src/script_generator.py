"""
Script Generator Module for SKILLOR Pipeline
FULLY FIXED - JSON Cleaning + Native Tone + Retention Optimization
"""

import json
import logging
import os
import re
import time

try:
    from groq import BadRequestError, Groq
except ImportError:  # lets offline validation/tests import this module
    Groq = None
    BadRequestError = Exception

# ============================================
# LOGGING CONFIGURATION
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# CONSTANTS
# ============================================
# One unified policy for a 20–26 second Body Glitch Short (FIXED 2026-08-02:
# the 40-55s format measured 27-38% average-view-percentage on this channel —
# viewers leave around ~10s, so the long format guarantees sub-50% retention
# and the feed demotes it. Six fast scenes give a complete explanation with a
# ~2.5-3s per-scene pace, the format that scored 59.65% retention here).
MIN_SCENES = 6
MAX_SCENES = 6
# 96 words at the cloned-voice pace reliably reaches ~40 seconds while
# leaving normal language room; forcing 104+ made the LLM pad or fail scenes.
def _duration_word_budget() -> tuple:
    """Word count derived from the ACTIVE duration target, not hardcoded.

    The duration A/B experiment sets TARGET_MIN/MAX_SECONDS per run. These
    constants used to be fixed at 86-110 words (~33-42s of narration), which
    silently broke the short arm: main.py aborts when narration exceeds
    TARGET_MAX * 1.12, so on a 26-32s target anything over ~93 words died —
    roughly 70% of the allowed range, and all 3 retries with it. The whole
    experiment arm would have produced nothing but failed runs.

    ~2.6 words/sec is the measured Kokoro FR pace on this channel.
    """
    import os as _os
    words_per_second = 2.6
    # FIXED 2026-08-02: default target is now the SHORT format (20-26s).
    # The old floor of max(40, ...) forced >=40 words (~15s narration) even
    # when a short arm was requested, silently breaking the whole experiment.
    target_min = float(_os.environ.get("TARGET_MIN_SECONDS", "20"))
    target_max = float(_os.environ.get("TARGET_MAX_SECONDS", "26"))
    # Aim inside the window with headroom: never plan narration longer than
    # the target max, since the pipeline aborts at target_max * 1.12.
    low = max(24, int(target_min * words_per_second * 0.85))
    high = max(low + 8, int(target_max * words_per_second * 0.92))
    return low, high


MIN_WORDS, MAX_WORDS = _duration_word_budget()
MAX_RETRIES = 3
SCRIPT_POLICY_VERSION = "BODY_GLITCH_V4_ANSWER_FIRST"
TEMPERATURE = 0.65
MAX_TOKENS = 1400

# A fast, clear opening that comfortably fits in the first 2–3 seconds.
HOOK_MIN_WORDS = 5
HOOK_MAX_WORDS = 9
# Short-format scene budget (FIXED 2026-08-02): 6 scenes x 7-10 words ≈
# 42-60 words ≈ 16-23s narration — the 20-26s target window.
MIN_SCENE_WORDS = 7
MAX_SCENE_WORDS = 10

# Interchangeable openers that name no phenomenon. Every one of these was
# measured on the live channel: the 11 videos starting this way average 11s
# watched on ~39s Shorts, because the first 2 seconds carry zero information.
# _validate_script() rejects a scene-1 caption starting with any of them.
GENERIC_HOOK_OPENERS = (
    "vous avez déjà", "vous avez probablement", "vous avez peut-être",
    "tu as déjà", "tu as probablement", "vous avez l'impression",
    "tu as l'impression", "vous avez ressenti", "tu as ressenti",
    "vous vous réveillez", "ça vous arrive", "ca vous arrive",
    "ça t'arrive", "n'avez-vous jamais", "navez-vous jamais",
    "saviez-vous que", "imaginez que", "il vous est déjà arrivé",
)

# Scene 2 must open with the mechanism itself (V4 answer-first arc).
ANSWER_FIRST_PREFIXES = (
    "c'est", "cest", "ton cerveau", "ton corps", "votre cerveau", "votre corps",
    "en fait", "la raison", "ce sont", "tes ", "vos ", "ton ", "votre ",
)

# A title such as "Why Got Fired Matters" is grammatically short but gives
# viewers no scientific subject. Require a concrete channel-relevant anchor.
TITLE_TOPIC_ANCHORS = {
    "cerveau", "corps", "sommeil", "mémoire", "coeur", "cœur", "yeux", "oeil", "œil",
    "ventre", "nerf", "hormone", "cellule", "sang", "immunité", "santé", "science",
    "espace", "nasa", "planète", "océan", "physique", "technologie", "robot", "ia",
    "anatomie", "biologie", "psychologie", "génétique", "virus",
}
# ============================================
# 1. SYSTEM PROMPT (NATIVE TONE + RETENTION)
# ============================================

def _get_system_prompt() -> str:
    """French editorial standard for a France-first science Shorts channel."""
    return """Tu écris des YouTube Shorts en français naturel, fluide et idiomatique,
sur la science, le corps humain et le cerveau, pour des adultes francophones.

RÈGLES DE QUALITÉ NON NÉGOCIABLES :
- Réponds intégralement en français de France, sans anglicismes ni traduction littérale.
- Explique une idée vérifiable et utile par vidéo, dans une langue simple et orale.
- Promets une curiosité précise dès l'ouverture, puis apporte réellement la réponse.
- N'invente jamais études, chiffres, citations, diagnostics, remèdes, dangers ou conseils médicaux.
- Évite la peur, l'urgence artificielle, les secrets, et les tournures clickbait.
- Chaque scène doit apporter une information nouvelle. Écris pour l'oral : phrases courtes et concrètes.
- Le CTA reste naturel et discret ; il ne doit pas être répété dans la narration.
- Retourne uniquement un JSON valide, sans Markdown ni commentaire.

RÈGLES D'ENGINEERING VIRAL (rétention) :
- Le HOOK (scène 1, 2-3s) doit créer un « vide de curiosité » : nommer le phénomène
  précis puis le laisser inexpliqué, pour forcer à regarder la suite (ex: « Pourquoi
  votre cœur s'emballe juste avant de vous endormir ? »). Un hook vague coûte la rétention.
- Donner la réponse-choc OU la promesse du mécanisme dans les 2 premières scènes,
  puis détailler — ne pas faire attendre la valeur au-delà de 5s.
- Chaque scène doit contenir UNE idée courte et concrète ; les phrases longues font
  chuter la rétention sur Shorts.
- Boucler la fin sur l'ouverture (référence au hook) pour encourager le rewatch.
"""

# ============================================
# 2. PROMPT GENERATION
# ============================================

def _default_prompt(topic: str) -> str:
    """Build a French-France short-form script brief."""
    body_glitch_mode = os.environ.get("CONTENT_SERIES", "").lower() == "body_glitches_fr"
    series_rules = """
RÈGLES SÉRIE « RÉFLEXES DU CORPS » :
- Traite un phénomène quotidien, familier et à faible risque.
- Adopte un ton calme, curieux et fiable ; pas de diagnostic, de traitement ou d'alarmisme.
- Explique ce qui se produit habituellement, avec une conclusion simple et prudente.
- Si nécessaire, rappelle que des symptômes nouveaux, persistants, sévères ou inquiétants justifient l'avis d'un professionnel qualifié.
""" if body_glitch_mode else ""
    # Duration comes from the active experiment arm, not a hardcoded range —
    # otherwise the LLM keeps writing 32-42s scripts while the pipeline is
    # targeting 26-32s, and every short-arm run aborts on narration length.
    # FIXED 2026-08-02: default is the SHORT format (20-26s, 6 scenes).
    target_min = int(float(os.environ.get("TARGET_MIN_SECONDS", "20")))
    target_max = int(float(os.environ.get("TARGET_MAX_SECONDS", "26")))
    return f"""
Crée un YouTube Short original de {target_min} à {target_max} secondes sur ce sujet :
SUJET : {topic}
{series_rules}

Utilise EXACTEMENT {MAX_SCENES} scènes et retourne le schéma JSON ci-dessous.

ARC NARRATIF COMPACT ({MAX_SCENES} scènes — LA RÉPONSE DÈS LA SCÈNE 2, les
analytics montrent que le spectateur part à ~10 s si la réponse tarde) :
1. ACCROCHE — scène 1 (0–3 s) ; RUPTURE DE PATTERN à la deuxième personne
   (« tu/vous/votre corps ») : nomme LE phénomène précis du sujet puis le
   détail inattendu qui crée une boucle ouverte. BON : « Pourquoi ta voix
   sonne morte chaque matin ? » / « Ton corps te fige avant un bruit qui
   fait peur. » MAUVAIS, INTERDIT : formules génériques réutilisables d'une
   vidéo à l'autre (« Vous avez déjà ressenti cela ? », « Ça vous arrive
   aussi ? ») ou phrases plates — chaque accroche est UNIQUE et cite le
   phénomène exact.
2. RÉPONSE FLASH — scène 2 ; LE MÉCANISME CENTRAL EN UNE PHRASE qui
   commence par « C'est… », « Ton cerveau… » ou « Ton corps… ». Le
   spectateur est récompensé immédiatement — et une nouvelle boucle
   s'ouvre (« mais comment ? »). Jamais de préparation ici.
3. MÉCANISME — scènes 3–5 ; comment ça marche, étape par étape, concret et
   oral. La scène 5 commence par une micro-relance : « Le plus étrange ? »,
   « Encore plus fort : » ou « Et surtout : ».
4. BOUCLE — scène {MAX_SCENES} ; retour satisfaisant à l'accroche, sans la
   répéter mot à mot, pour relancer un nouveau visionnage.

RÈGLES DE FORMAT :
- Total des légendes parlées : {MIN_WORDS}–{MAX_WORDS} mots français.
- Scène 1 : {HOOK_MIN_WORDS}–{HOOK_MAX_WORDS} mots. Scènes 2–{MAX_SCENES} : {MIN_SCENE_WORDS}–{MAX_SCENE_WORDS} mots chacune.
- `hook` doit correspondre exactement à la légende de la scène 1.
- Visuel scène 1 : GROS PLAN humain concret (bouche devant un miroir, main sur
  la poitrine, yeux qui s'ouvrent au réveil) — un visage/proche arrête le
  scroll, un plan large abstrait non.
- Chaque scène doit avoir un visuel distinct de 5 à 12 mots, sans texte, logo ni interface.
- Titre : cinq à huit mots qui OUVRENT UNE BOUCLE DE CURIOSITÉ avec « Pourquoi »
  ou « ton/ta/votre » — BON : « Pourquoi ton cœur bat la nuit » · « Pourquoi
  ton corps se fige de peur ». MAUVAIS (rejeté) : étiquettes de 1-3 mots comme
  « Voix du matin », « Choc anaphylactique » — zéro clic.
- `thumbnail_text` : 2 à 4 mots clairs qui complètent le titre sans le répéter.
- `cta` : une invitation courte et naturelle à s'abonner, uniquement en métadonnée.
- `description` : une phrase exacte qui résume l'explication.

JSON UNIQUEMENT :
{{"title":"...","thumbnail_text":"...","hook":"...","scenes":[{{"visual":"...","caption":"..."}}],"cta":"...","description":"..."}}
"""

# ============================================
# 3. JSON CLEANING FUNCTION
# ============================================

def _clean_json_response(raw_reply: str) -> dict:
    """
    Cleans and extracts JSON from LLM response.
    Handles markdown code blocks, extra text, and malformed JSON.
    """
    if not raw_reply:
        raise ValueError("Empty response from LLM")
    
    # Remove markdown code blocks
    raw_reply = re.sub(r'```json\s*', '', raw_reply)
    raw_reply = re.sub(r'```\s*', '', raw_reply)
    
    # Try to find JSON object
    json_match = re.search(r'\{.*\}', raw_reply, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
    else:
        json_str = raw_reply
    
    # Clean common JSON issues
    json_str = json_str.strip()
    
    # Fix trailing commas
    json_str = re.sub(r',\s*}', '}', json_str)
    json_str = re.sub(r',\s*]', ']', json_str)
    
    # NOTE: We intentionally do NOT blanket-convert single quotes to double
    # quotes here. Groq's response_format={"type": "json_object"} already
    # guarantees valid double-quoted JSON, and the system prompt asks for
    # natural contractions ("don't", "you're"), which contain apostrophes.
    # Converting those apostrophes to '"' corrupts the JSON mid-string
    # (this was the root cause of the "Expecting ',' delimiter" errors).
    
    # Remove control characters
    json_str = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
    
    # Fix unescaped newlines in strings
    json_str = re.sub(r'(?<!\\)\n', ' ', json_str)
    
    # Try to parse
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parsing failed: {e}")
        logger.debug(f"Cleaned JSON: {json_str[:500]}...")
        
        # Fallback: Try to extract with regex
        fallback = {}
        
        # Extract title
        title_match = re.search(r'"title"\s*:\s*"([^"]+)"', json_str)
        if title_match:
            fallback['title'] = title_match.group(1)
        
        # Extract hook
        hook_match = re.search(r'"hook"\s*:\s*"([^"]+)"', json_str)
        if hook_match:
            fallback['hook'] = hook_match.group(1)
        
        # Extract scenes
        scenes_match = re.search(r'"scenes"\s*:\s*\[(.*?)\]', json_str, re.DOTALL)
        if scenes_match:
            scenes_str = scenes_match.group(1)
            scenes = []
            # Find all scene objects
            scene_blocks = re.finditer(r'\{[^{}]*\}', scenes_str, re.DOTALL)
            for block in scene_blocks:
                scene_str = block.group(0)
                visual_match = re.search(r'"visual"\s*:\s*"([^"]+)"', scene_str)
                caption_match = re.search(r'"caption"\s*:\s*"([^"]+)"', scene_str)
                if visual_match and caption_match:
                    scenes.append({
                        'visual': visual_match.group(1),
                        'caption': caption_match.group(1)
                    })
            if scenes:
                fallback['scenes'] = scenes
        
        # Extract CTA
        cta_match = re.search(r'"cta"\s*:\s*"([^"]+)"', json_str)
        if cta_match:
            fallback['cta'] = cta_match.group(1)
        
        # Extract description
        desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', json_str)
        if desc_match:
            fallback['description'] = desc_match.group(1)
        
        if fallback:
            logger.info("✅ Extracted data using regex fallback")
            return fallback
        
        raise ValueError(f"Could not parse JSON from response: {raw_reply[:200]}") from e


# ============================================
# 4. SCRIPT VALIDATION & NORMALIZATION
# ============================================

def _trim_to_word_limit(caption: str, max_words: int) -> str:
    """Trim a caption down to at most max_words, preferring to stop at the
    last complete sentence within the limit; falls back to a hard cut with
    a trailing period. Used to auto-fix scenes the LLM wrote too long,
    instead of burning a full retry (and more Groq tokens) over something
    a simple trim already fixes."""
    words = caption.split()
    if len(words) <= max_words:
        return caption
    truncated = " ".join(words[:max_words])
    # Prefer cutting at the last sentence-ending punctuation in range.
    # The old >=50% floor forced the hard-cut fallback, which shipped
    # MID-SENTENCE voiceovers (see production history). Early-but-complete
    # beats broken every time; _validate_script retries if it comes out
    # too short — regeneration is better than broken audio.
    last_stop = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_stop >= len(truncated) * 0.3:
        return truncated[:last_stop + 1]
    # No sentence boundary: cut at the last clause boundary so the spoken
    # line still sounds like a deliberate end, not a crash.
    clause_floor = len(truncated) * 0.4
    for sep in (";", "—", ",", ":"):
        idx = truncated.rfind(sep)
        if idx >= clause_floor:
            return truncated[:idx].rstrip() + "."
    truncated = truncated.rstrip(",;:")
    if not truncated.endswith((".", "!", "?")):
        truncated += "."
    return truncated


def _normalize_scenes(script_data: dict) -> dict:
    """
    Normalizes scene data from various formats.
    Ensures all required fields are present.
    """
    normalized = []
    
    for s in script_data.get('scenes', []):
        # Try different field names
        visual = s.get('visual') or s.get('description') or s.get('image') or ''
        caption = s.get('caption') or s.get('text') or s.get('speech') or ''
        
        # Clean and validate
        visual = visual.strip()
        caption = caption.strip()
        
        if visual and caption:
            normalized.append({
                "visual": visual,
                "caption": caption
            })
        elif caption and not visual:
            # If only caption exists, generate a generic visual
            normalized.append({
                "visual": f"Dark cinematic shot of {caption[:30]}...",
                "caption": caption
            })

    # Auto-fix: trim any scene that's over its word limit instead of
    # spending a full LLM retry on something a simple trim already solves.
    # Scene 1 (the hook) has a tighter cap - see _validate_script for why.
    for i, scene in enumerate(normalized):
        limit = HOOK_MAX_WORDS if i == 0 else MAX_SCENE_WORDS
        scene['caption'] = _trim_to_word_limit(scene['caption'], limit)

    script_data['scenes'] = normalized
    script_data['voiceover'] = ' '.join(s['caption'] for s in normalized)

    # Auto-fix: the scored hook must be the exact line viewers hear first.
    # Rather than relying on the LLM to retype the hook identically to
    # scene 1's caption (a common, easy mistake for smaller models), just
    # force them to match - scene 1's caption is the source of truth since
    # that's what's actually spoken.
    if normalized:
        script_data['hook'] = normalized[0]['caption']

    return script_data


def _validate_script(script_data: dict) -> tuple[bool, list[str]]:
    """
    Validates script for quality and completeness.
    
    Returns:
        (is_valid, issues_list)
    """
    issues = []
    
    # Check required fields
    required_fields = ['title', 'hook', 'scenes', 'cta']
    for field in required_fields:
        if not script_data.get(field):
            issues.append(f"Missing required field: {field}")

    # main.py replaces temporary LLM titles with the deterministic Body
    # Glitch episode title before SEO/upload. Do not burn API retries over
    # title word counts here; the published title is validated by the series.
    # Check scenes
    scenes = script_data.get('scenes', [])
    if len(scenes) < MIN_SCENES:
        issues.append(f"Too few scenes: {len(scenes)} (minimum {MIN_SCENES})")
    elif len(scenes) > MAX_SCENES:
        issues.append(f"Too many scenes: {len(scenes)} (maximum {MAX_SCENES})")
    
    # Check word count
    voiceover = script_data.get('voiceover', '')
    word_count = len(voiceover.split())
    if word_count < MIN_WORDS:
        issues.append(f"Too few words: {word_count} (minimum {MIN_WORDS})")
    elif word_count > MAX_WORDS:
        issues.append(f"Too many words: {word_count} (maximum {MAX_WORDS})")
    
    # Check each scene
    # (HOOK_MIN_WORDS/HOOK_MAX_WORDS/MAX_SCENE_WORDS are the same constants
    # _normalize_scenes already auto-trims to, so a script that's been
    # normalized should always pass this - this check is now mostly a
    # safety net for anything normalization didn't catch.)
    for i, scene in enumerate(scenes):
        if not scene.get('visual'):
            issues.append(f"Scene {i+1} missing visual description")
        if not scene.get('caption'):
            issues.append(f"Scene {i+1} missing caption")
        else:
            scene_words = len(scene['caption'].split())
            if i == 0:
                if scene_words < HOOK_MIN_WORDS or scene_words > HOOK_MAX_WORDS:
                    issues.append(
                        f"Scene {i+1} (hook) has {scene_words} words "
                        f"(allowed {HOOK_MIN_WORDS}-{HOOK_MAX_WORDS} to stay under the 4s hook-duration gate)"
                    )
            elif scene_words > MAX_SCENE_WORDS:
                issues.append(f"Scene {i+1} has {scene_words} words (maximum {MAX_SCENE_WORDS})")

    # The scored hook must be the line viewers actually hear first.
    if scenes and script_data.get('hook'):
        def norm(value):
            return re.sub(r"[^a-z0-9 ]", "", value.lower()).strip()
        hook = norm(script_data['hook'])
        first = norm(scenes[0].get('caption', ''))
        if hook != first:
            issues.append("Hook must exactly match the first scene caption")

    # ------------------------------------------------------------------
    # STORY ARC ENFORCEMENT — the prompt demands Accroche → Suspense → …
    # → Réponse → Boucle, but nothing enforced it. YouTube Shorts ranks on
    # first-3s swipe survival + completion + replays: an open question in
    # scene 2 and a closing loop pointing back to the hook are the cheapest
    # retention levers. A script missing them is retried, never shipped.
    # ------------------------------------------------------------------
    if len(scenes) >= 3:
        # SCENE 1 — BANNED GENERIC OPENERS.
        # Analytics autopsy (2026-07-26, 9 videos with data): average view
        # duration is 11s on ~39s Shorts (27.5% retention) and viewers leave
        # around scene 2.2/8 — i.e. DURING the setup. 11 of 17 published
        # videos open with an interchangeable filler ("Vous avez déjà…",
        # "Vous vous réveillez…") that names no phenomenon and burns the
        # entire 2-second swipe window. The prompt already forbids this, but
        # nothing enforced it, so the LLM kept shipping it. Now it retries.
        hook_caption = scenes[0].get('caption', '').strip()
        hook_norm = re.sub(r"[^a-zà-ÿœ' ]", "", hook_caption.lower()).strip()
        for opener in GENERIC_HOOK_OPENERS:
            if hook_norm.startswith(opener):
                issues.append(
                    f"Scene 1 (ACCROCHE) starts with the banned generic opener "
                    f"'{opener}…' — name the exact phenomenon in the first 3 words "
                    f"instead (viewers swipe at ~2s on openers like this)."
                )
                break

        # SCENE 2 — must DELIVER, not stall. V4 (BODY_GLITCH_V4_ANSWER_FIRST)
        # moved the answer to scene 2; this check previously demanded a
        # QUESTION there, directly contradicting the prompt and rewarding the
        # exact "setup drags on" pattern that loses viewers at scene 2.2.
        answer = scenes[1].get('caption', '').strip()
        answer_norm = answer.lower()
        starts_with_answer = any(
            answer_norm.startswith(p) for p in ANSWER_FIRST_PREFIXES
        )
        if not starts_with_answer:
            issues.append(
                "Scene 2 (RÉPONSE FLASH) must deliver the mechanism immediately, "
                "starting with « C'est… », « Ton cerveau… », « Ton corps… » or "
                "« En fait… ». Viewers leave at ~scene 2 — the payoff must land there."
            )
        if answer.endswith('?'):
            issues.append(
                "Scene 2 must ANSWER, not ask another question — the open loop "
                "belongs in scene 1."
            )
        hook_concepts = _content_concepts(scenes[0].get('caption', ''))
        tail_concepts = _content_concepts(scenes[-1].get('caption', ''))
        if hook_concepts and not (hook_concepts & tail_concepts):
            issues.append(
                "Final scene (LOOP-BACK) must echo the opening idea — share at "
                "least one concept word with the hook so the Short loops "
                "cleanly (replay = ranking signal)."
            )

    return len(issues) == 0, issues


_ARC_STOPWORDS = {
    # English (shared codepath)
    "this", "that", "with", "from", "your", "yours", "when", "what", "why",
    "how", "have", "has", "been", "there", "their", "they", "them", "about",
    "just", "like", "over", "under", "more", "most", "some", "into", "also",
    "very", "than", "then", "these", "those", "because", "while", "after",
    "before", "people", "really", "actually", "don't", "doesn't", "every",
    "many", "much", "feel", "feels", "thing", "things", "body",
    # French — without these, function words would create false-overlap
    # between hook and loop-back for fr-FR scripts. (A real example caught
    # by the tests: "pendant" appears in almost every sentence and faked
    # the loop-back match.)
    "votre", "vous", "avec", "pour", "dans", "cette", "quand", "pourquoi",
    "comment", "mais", "plus", "très", "être", "avoir", "nous", "tout",
    "tous", "toute", "fait", "faite", "aussi", "encore", "comme", "chose",
    "choses", "corps", "bien", "dont", "leur", "leurs", "elles", "alors",
    "peut", "faut", "sans", "soit", "rien", "jamais", "toujours", "parce",
    "notre", "nos", "vos", "ceci", "cela", "celles", "ceux",
    "quoi", "quel", "quelle", "même", "moins", "vraiment", "souvent",
    "pendant", "après", "avant", "entre", "chez", "vers", "depuis",
    "contre", "selon", "afin", "grâce", "malgré", "enfin", "puis", "dès",
    "voici", "voilà", "autre", "autres", "chaque", "veut", "sont",
    "avons", "avez", "suis", "es", "est", "était", "sera",
}


def _content_concepts(text: str) -> set:
    """Stem-ish concept words for arc-overlap checks: lowercase, punctuation
    stripped, stopwords and short words removed, naive trailing-'s' fold so
    plurals/singulars collide in both English and French."""
    concepts = set()
    for raw in re.sub(r"[^a-z0-9àâäçéèêëîïôöùûüÿœæ ]", " ", text.lower()).split():
        if len(raw) <= 3 or raw in _ARC_STOPWORDS:
            continue
        stem = raw.rstrip("s")  # crude plural fold (works for FR too)
        concepts.add(stem if len(stem) > 3 else raw)
    return concepts


# ---------------------------------------------------------------------------
# PUBLIC API — stable importable interface.
# ---------------------------------------------------------------------------

def validate_script(script_data: dict) -> tuple[bool, list[str]]:
    """Validate a generated script for structural completeness.

    Public wrapper around the internal ``_validate_script``.
    Use this from external code (quality_checker, tests, etc.)
    instead of importing the underscore-prefixed version.

    Parameters
    ----------
    script_data : dict
        Script dictionary with 'title', 'hook', 'scenes', 'cta', 'voiceover'.

    Returns
    -------
    tuple[bool, list[str]]
        (is_valid, issues_list)
    """
    return _validate_script(script_data)


# ============================================
# 5. RETENTION ANALYSIS
# ============================================

def analyze_retention_potential(script_data: dict) -> dict:
    """
    Analyzes script for retention potential.
    Returns score (0-100) and suggestions.
    """
    scenes = script_data.get('scenes', [])
    score = 0
    suggestions = []
    
    # Check scene count
    if MIN_SCENES <= len(scenes) <= MAX_SCENES:
        score += 20
    else:
        suggestions.append(f"Optimal scene count: {MIN_SCENES}-{MAX_SCENES}, currently {len(scenes)}")
    
    # Check hook
    hook = script_data.get('hook', '')
    if hook:
        hook_words = len(hook.split())
        if HOOK_MIN_WORDS <= hook_words <= HOOK_MAX_WORDS:
            score += 15
        else:
            suggestions.append(f"Hook should be {HOOK_MIN_WORDS}-{HOOK_MAX_WORDS} words for a fast, clear opening")
        
        # Check for pattern interrupt
        if len(hook.split()) <= 9 and any(ch in hook for ch in ['?', '.', '!']):
            score += 10
    
    # Check "YOU" language
    voiceover = script_data.get('voiceover', '')
    you_count = sum(voiceover.lower().count(word) for word in ('vous', 'votre', 'tu', 'ton'))
    if you_count >= 2:
        score += 15
    else:
        suggestions.append("Use the viewer naturally once or twice where it helps clarity")
    
    # Check cliffhangers
    cliffhanger_count = 0
    for scene in scenes:
        caption = scene.get('caption', '')
        if any(word in caption.lower() for word in ['...', 'mais', 'pourtant', 'alors', 'et si']):
            cliffhanger_count += 1
    
    if 1 <= cliffhanger_count <= 3:
        score += 20
    else:
        suggestions.append(f"Only {cliffhanger_count}/{len(scenes)} scenes have cliffhangers - use only 1-3 natural open loops")
    
    # Check word count
    word_count = len(voiceover.split())
    if MIN_WORDS <= word_count <= MAX_WORDS:
        score += 20
    else:
        suggestions.append(f"Word count: {word_count} (target: {MIN_WORDS}-{MAX_WORDS})")
    
    # Check for loopable outro
    cta = script_data.get('cta', '')
    if any(word in cta.lower() for word in ['abonne', 'partage', 'commente', 'suivez']):
        score += 10
    
    return {
        'retention_score': min(100, score),
        'suggestions': suggestions,
        'scenes': len(scenes),
        'word_count': word_count,
        'you_count': you_count,
        'cliffhanger_ratio': cliffhanger_count / len(scenes) if scenes else 0,
        'is_viral_ready': score >= 80
    }


# ============================================
# 6. MAIN GENERATE FUNCTION
# ============================================

def generate_script(
    topic: str, 
    custom_prompt: str | None = None, 
    max_retries: int = MAX_RETRIES
) -> dict:
    """
    Generates a RETENTION-OPTIMIZED script using Groq LLM.
    
    Features:
    - JSON cleaning with regex fallback
    - Native English tone enforcement
    - Automatic validation and retry
    - Retention analysis
    
    Args:
        topic: Topic for the script
        custom_prompt: Optional custom prompt
        max_retries: Maximum retry attempts
    
    Returns:
        Script data dictionary
    
    Raises:
        RuntimeError: If generation fails after all retries
        ValueError: If GROQ_API_KEY is missing
    """
    logger.info(
        "Script policy %s: %s scenes, %s-%s words; temporary title is not a retry gate.",
        SCRIPT_POLICY_VERSION, MIN_SCENES, MIN_WORDS, MAX_WORDS,
    )

    # Check API key
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is missing. Please set it in environment variables.")
    
    # Initialize client only for an actual generation call. Structural checks
    # and offline tests do not require the optional runtime dependency.
    if Groq is None:
        raise RuntimeError("groq package is not installed; run pip install -r requirements.txt")
    client = Groq(api_key=api_key)
    
    # Prepare prompt
    prompt = custom_prompt or _default_prompt(topic)
    messages = [
        {"role": "system", "content": _get_system_prompt()},
        {"role": "user", "content": prompt}
    ]
    
    last_error = None
    best_script = None
    best_score = 0
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔄 Generating script (Attempt {attempt}/{max_retries})")
            
            # Call Groq API
            completion = client.chat.completions.create(
                messages=messages,
                # Overridable via GROQ_MODEL. The 8B instant model is fast/cheap
                # but produces weaker French hooks/titles; a 70B class model
                # (set in the workflow) materially improves curiosity-driven
                # openings and clickable titles -> better CTR/retention.
                model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                response_format={"type": "json_object"},
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS
            )
            
            raw_reply = completion.choices[0].message.content
            
            # Clean JSON
            script_data = _clean_json_response(raw_reply)
            
            # Normalize scenes
            script_data = _normalize_scenes(script_data)
            
            # Add metadata
            script_data['topic'] = topic
            script_data['generated_at'] = time.time()
            script_data['attempt'] = attempt
            
            # Validate
            is_valid, issues = _validate_script(script_data)
            
            if is_valid:
                # Analyze retention
                retention = analyze_retention_potential(script_data)
                script_data['retention_analysis'] = retention
                
                score = retention['retention_score']
                
                # Track best script
                if score > best_score:
                    best_script = script_data
                    best_score = score
                
                if score >= 80:
                    logger.info(f"✅ Excellent script! Retention score: {score}/100")
                    logger.info(f"📊 {len(script_data['scenes'])} scenes, {len(script_data['voiceover'].split())} words")
                    # FEEDBACK LOOP: persist this script as part of the channel
                    # baseline so the NEXT script compares against it.
                    try:
                        from viral_baseline import record_script
                        record_script(script_data, score)
                    except Exception as exc:
                        logger.warning("Baseline record skipped: %s", exc)
                    return script_data
                else:
                    logger.warning(f"⚠️ Good but could be better (Score: {score}/100)")
                    # Add corrective feedback
                    messages.append({"role": "assistant", "content": raw_reply})
                    baseline_fb = ""
                    try:
                        from viral_baseline import feedback_to_beat_baseline
                        baseline_fb = " | ".join(feedback_to_beat_baseline(script_data, score))
                    except Exception as exc:
                        logger.warning("Baseline feedback skipped: %s", exc)
                    messages.append({"role": "user", "content": (
                        f"The script is good but retention could be improved. "
                        f"Current score: {score}/100. Issues: {', '.join(retention['suggestions'][:3])}. "
                        + (f"BEAT THE CHANNEL BASELINE: {baseline_fb}. " if baseline_fb else "")
                        + f"Rewrite the script with these improvements while keeping the topic '{topic}'. "
                        f"Return ONLY valid JSON with the same structure."
                    )})
            else:
                last_error = "; ".join(issues)
                logger.warning(f"⚠️ Validation issues: {', '.join(issues[:3])}")
                messages.append({"role": "assistant", "content": raw_reply})
                messages.append({"role": "user", "content": (
                    f"The script has validation issues: {', '.join(issues[:3])}. "
                    f"Rewrite it to fix these issues. Keep the same topic '{topic}'. "
                    f"Return ONLY valid JSON with the same structure."
                )})
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing failed: {e}")
            messages.append({"role": "user", "content": (
                "The previous response was not valid JSON. "
                "Please return ONLY valid JSON with this exact structure: "
                '{"title": "...", "hook": "...", "scenes": [{"visual": "...", "caption": "..."}], "cta": "..."}'
            )})
            
        except BadRequestError as e:
            logger.error(f"❌ Groq API error: {e}")
            last_error = e
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.info(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                break
            
        except Exception as e:
            # Handle Groq rate limits with proper wait
            err_str = str(e)
            if "rate_limit" in err_str or "429" in err_str:
                import re as _re
                m = _re.search(r"try again in (\d+)m(\d+)?", err_str)
                wait_sec = 300
                if m:
                    mins = int(m.group(1))
                    secs = int(m.group(2)) if m.group(2) else 0
                    wait_sec = mins * 60 + secs + 10
                logger.warning("Groq rate limited — waiting %ds", wait_sec)
                time.sleep(wait_sec)
                continue
            logger.error(f"❌ Unexpected error: {e}")
            last_error = e
            if attempt < max_retries:
                wait_time = 2 ** attempt
                logger.info(f"⏳ Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
    
    # If we have a best script, return it
    if best_script:
        logger.warning(f"⚠️ Using best available script (Score: {best_score}/100)")
        return best_script
    
    # Complete failure
    raise RuntimeError(
        f"❌ Script generation failed after {max_retries} attempts. "
        f"Last error: {last_error}"
    )


# ============================================
# 7. BATCH GENERATION
# ============================================

def generate_multiple_scripts(
    topics: list[str],
    max_retries: int = MAX_RETRIES,
    delay: float = 2.0
) -> list[dict]:
    """
    Generates scripts for multiple topics.
    
    Args:
        topics: List of topics
        max_retries: Retries per script
        delay: Delay between generations
    
    Returns:
        List of script data dictionaries
    """
    scripts = []
    failed = []
    
    for i, topic in enumerate(topics):
        logger.info(f"📝 Generating script {i+1}/{len(topics)}: {topic}")
        
        try:
            script = generate_script(topic, max_retries=max_retries)
            scripts.append(script)
            logger.info(f"✅ Script {i+1} generated successfully")
        except Exception as e:
            logger.error(f"❌ Script {i+1} failed: {e}")
            failed.append({'topic': topic, 'error': str(e)})
        
        if i < len(topics) - 1:
            time.sleep(delay)
    
    logger.info(f"📊 Generated {len(scripts)}/{len(topics)} scripts successfully")
    if failed:
        logger.warning(f"⚠️ Failed scripts: {len(failed)}")
    
    return scripts, failed


# ============================================
# 8. SCRIPT EXPORT
# ============================================

def export_script(script_data: dict, output_path: str = "output/script.json") -> str:
    """
    Exports script data to JSON file.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(script_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"📄 Script exported to: {output_path}")
    return output_path


# ============================================
# 9. MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    print("="*70)
    print("SCRIPT GENERATOR - FULLY FIXED (JSON Cleaning + Native Tone)")
    print("="*70)
    print()
    
    # Test single generation
    test_topic = "Why Your Brain Lies to You"
    print(f"🧪 Testing with topic: {test_topic}")
    print("-" * 70)
    
    try:
        script = generate_script(test_topic)
        
        print("✅ Script generated successfully!")
        print()
        print(f"📌 TITLE: {script.get('title')}")
        print(f"🎯 HOOK: {script.get('hook')}")
        print(f"📊 SCENES: {len(script.get('scenes', []))}")
        print(f"📝 WORDS: {len(script.get('voiceover', '').split())}")
        print(f"📢 CTA: {script.get('cta')}")
        
        if 'retention_analysis' in script:
            analysis = script['retention_analysis']
            print()
            print("📈 RETENTION ANALYSIS:")
            print(f"   Score: {analysis.get('retention_score')}/100")
            print(f"   Viral Ready: {analysis.get('is_viral_ready')}")
            if analysis.get('suggestions'):
                print("   Suggestions:")
                for suggestion in analysis['suggestions'][:3]:
                    print(f"     - {suggestion}")
        
        print()
        print("📄 FIRST SCENE PREVIEW:")
        scenes = script.get('scenes', [])
        if scenes:
            print(f"   Visual: {scenes[0].get('visual')}")
            print(f"   Caption: {scenes[0].get('caption')}")
        
        print()
        print("-" * 70)
        print("✅ Script generator is ready for production!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
