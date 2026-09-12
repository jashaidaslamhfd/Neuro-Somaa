"""
Niche Strategy Module for SKILLOR Pipeline
OPTIMIZED FOR: DARK PSYCHOLOGY — HIGH RETENTION + CURIOUSITY PACING

2026 UPDATE:
- Topic pool expanded from 150 → 360+ static topics
- Dynamic LLM topic generation when pool runs low
- Clickbait hooks removed (YouTube penalizes "Doctors don't want" patterns)
- Engagement-bait CTAs removed (YouTube penalizes "like if", "comment 🤯")
- All hooks/CTAs are honest, curiosity-driven, natural-sounding
"""

import logging
import random
import re

logger = logging.getLogger(__name__)

# ============================================
# 1. DARK PSYCHOLOGY TOPICS (360+ French topics)
# ============================================
DARK_TOPICS = [
    "Pourquoi tu dis oui alors que tu veux dire non",
    "Pourquoi les menteurs ne regardent PAS toujours à gauche",
    "Pourquoi les gens te manipulent sans que tu le voies",
    "Pourquoi tu obéis à l'autorité sans réfléchir",
    "Pourquoi le pouvoir change ta personnalité en 7 jours",
    "Pourquoi le regard des autres influence tes décisions",
    "Pourquoi le mensonge le plus courant au monde est dit chaque jour",
    "Pourquoi tu fais confiance aux gens qui te mentent",
    "Pourquoi les manipulateurs utilisent ton prénom pour te contrôler",
    "Pourquoi tu acceptes des choses que tu n'accepterais pas seul",
    "Pourquoi le silence est l'arme de manipulation la plus puissante",
    "Pourquoi tu ne remarques pas quand quelqu'un te contrôle",
    "Pourquoi la loi du silence protège les abuseurs",
    "Pourquoi les personnes les plus dangereuses sont les plus charmantes",
    "Pourquoi tu ne vois pas quand quelqu'un t'aime vraiment",
    "Pourquoi la jalousie révèle ta peur pas ton amour",
    "Pourquoi tu pardones quand tu ne devrais pas pardonner",
    "Pourquoi ton besoin d'approbation te rend fragile",
    "Pourquoi tu crois être indépendant mais tu ne l'es pas",
    "Pourquoi tu utilises l'humour pour cacher ta douleur",
    "Pourquoi tu n'oses pas dire non alors que tu le devrais",
    "Pourquoi tu fais semblant d'aller bien alors que tu souffres",
    "Pourquoi tu évites les conflits même quand tu as raison",
    "Pourquoi tu restes dans des situations toxiques par habitude",
    "Pourquoi tu ne demandes pas de l'aide par orgueil",
    "Pourquoi tu te sens coupable sans avoir fait quoi que ce soit",
    "Pourquoi tu parles de toi soit trop peu soit trop",
    "Pourquoi tu attends la permission des autres pour être heureux",
    "Pourquoi les gens parlent de toi beaucoup plus que tu ne le crois",
    "Pourquoi tu mens pour protéger les autres pas toi-même",
    "Pourquoi le charme est souvent un masque dangereux",
    "Pourquoi le contrôle progressif est si difficile à détecter",
    "Pourquoi le pouvoir attire les pires personnes",
    "Pourquoi les institutions t'enseignent l'obéissance sans que tu le voies",
    "Pourquoi tu ne choisis pas librement tes opinions",
    "Pourquoi tu suis la majorité même quand elle a tort",
    "Pourquoi les algorithmes contrôlent ce que tu penses",
    "Pourquoi les réseaux sociaux exploitent les failles de ton cerveau",
    "Pourquoi l'école enseigne l'obéissance plus que la pensée critique",
    "Pourquoi la propagande utilise les mêmes techniques depuis 100 ans",
    "Pourquoi le silence met les gens tellement mal à l'aise qu'ils avouent",
    "Pourquoi les yeux ne mentent jamais même quand la bouche ment",
    "Pourquoi ton corps copie les gestes des autres sans que tu le saches",
    "Pourquoi la distance physique révèle tes vrais sentiments",
    "Pourquoi ta posture change comment les gens te voient",
    "Pourquoi tu rougis quand tu mens sans pouvoir le contrôler",
    "Pourquoi tes mains trahissent ton stress même en silence",
    "Pourquoi ton visage révèle tes émotions même si tu les caches",
    "Pourquoi le regard parental a défini ta valeur",
    "Pourquoi tu as peur secrètement de devenir comme tes parents",
    "Pourquoi ton cerveau te ment chaque jour",
    "Pourquoi tu crois être meilleur que la moyenne",
    "Pourquoi ton cerveau ne te montre que ce que tu veux voir",
    "Pourquoi ton cerveau invente des souvenirs qui ne sont jamais arrivés",
    "Pourquoi tu te souviens de ce qui te fait peur pas du bonheur",
    "Pourquoi le prix influence ce que tu aimes vraiment",
    "Pourquoi tu fais une erreur cognitive que 99% des gens font",
    "Pourquoi ton cerveau déteste perdre plus qu'il n'aime gagner",
    "Pourquoi ton cerveau juge tout le monde en 7 secondes",
    "Pourquoi tu oublies les bons moments plus vite que les mauvais",
    "Pourquoi ton cerveau refuse de changer d'avis face à la preuve",
    "Pourquoi tu te crois objectif mais ton jugement est biaisé",
    "Pourquoi tu imites les gens que tu admires sans le savoir",
    "Pourquoi tu ne connais pas ta vraie personnalité cachée",
    "Pourquoi tu n'es pas aussi intelligent que tu le crois",
    "Pourquoi ton cerveau décide avant que tu ne le saches",
    "Pourquoi tu choisis ce qui te convient pas ce qui est vrai",
    "Pourquoi tu ne te souviens pas de 90% de ta journée",
    "Pourquoi tu te compares aux autres en permanence",
    "Pourquoi tu ne vois que ce que tu veux voir",
    "Pourquoi ton cerveau traite la peur plus vite que la logique",
    "Pourquoi tu ressens le rejet comme une douleur physique",
    "Pourquoi ton cerveau crée des faux souvenirs en boucle",
    "Pourquoi tu te souviens des humiliations mais pas des victoires",
    "Pourquoi ton cerveau invente des solutions qui n'existent pas",
    "Pourquoi la répétition rend un mensonge plus crédible qu'une vérité",
    "Pourquoi ton cerveau associe les visages aux émotions pas aux noms",
    "Pourquoi tu remarques plus ce qui confirme ce que tu crois déjà",
    "Pourquoi tu juges un livre par sa couverture en 7 secondes",
    "Pourquoi tu fais la même erreur que tout le monde avec ton argent",
    "Pourquoi le biais de confirmation est le piège le plus dangereux",
    "Pourquoi ton cerveau exagère les dangers et minimise les chances",
    "Pourquoi tu surestimes ce que tu connais bien",
    "Pourquoi le prix d'un médicament influence son efficacité perçue",
    "Pourquoi ton cerveau cherche des patterns même là où il n'y en a pas",
    "Pourquoi tu te rappelles mal les conversations importantes",
    "Pourquoi les/news fausses se propagent plus vite que les vraies",
    "Pourquoi ton cerveau simplifie tout en catégories fausses",
    "Pourquoi tu crois contrôler tes choix alors que tu les subis",
    "Pourquoi le temps passe plus vite quand tu vieillis",
    "Pourquoi tu tombes toujours amoureux du mauvais type",
    "Pourquoi le silence fait plus de dégâts que les mots",
    "Pourquoi tu repenses toujours à cette humiliation",
    "Pourquoi tu attires dans ta vie ce que tu fuis le plus",
    "Pourquoi tu ne vois pas les signes quand quelqu'un t'aime vraiment",
    "Pourquoi tu acceptes des excuses que tu ne devrais pas accepter",
    "Pourquoi tu es accro à ton téléphone sans le savoir",
    "Pourquoi tu vérifies ton téléphone 100 fois par jour",
    "Pourquoi les réseaux sociaux sont conçus comme une drogue",
    "Pourquoi tu scrolles 3 heures sans t'en rendre compte",
    "Pourquoi tu te sens anxious quand ton téléphone est loin",
    "Pourquoi la dopamine te pousse à faire des choses stupides",
    "Pourquoi tu manges pour tes émotions pas pour ta faim",
    "Pourquoi tu procrastines par peur de réussir",
    "Pourquoi tu achètes des choses pour combler un vide émotionnel",
    "Pourquoi tu restes éveillé par peur de dormir",
    "Pourquoi la peur du rejet est plus forte que la peur de la mort",
    "Pourquoi tu préfères la douleur connue au bonheur inconnu",
    "Pourquoi tu utilises le travail pour fuir tes émotions",
    "Pourquoi tu te sous-estimes sans raison objective",
    "Pourquoi le conflit te fait plus peur que la solitude",
    "Pourquoi tu as peur de réussir autant que d'échouer",
    "Pourquoi tu préfères souffrir en silence que demander de l'aide",
    "Pourquoi tu as peur du jugement même de parfaits inconnus",
    "Pourquoi le regard de tes parents a défini ta valeur",
    "Pourquoi tu répètes les erreurs de tes parents sans le vouloir",
    "Pourquoi les blessures d'enfance cachent ta vraie personnalité",
    "Pourquoi tu cherches dans l'amour ce que tes parents ne t'ont pas donné",
    "Pourquoi tu ne sais pas dire non parce qu'on ne te l'a pas appris",
    "Pourquoi tu as peur secrètement de devenir comme tes parents",
    "Pourquoi ton métier est un choix émotionnel pas logique",
    "Pourquoi tu ne sais pas ce que tu veux vraiment dans la vie",
    "Pourquoi tu fuis les conversations profondes par peur",
    "Pourquoi tu te sens vide après avoir atteint un objectif",
    "Pourquoi tu fais des choses que tu ne comprends pas toi-même",
    "Pourquoi ta colère refoulée te détruit de l'intérieur",
    "Pourquoi tu n'oses pas dire la vérité par peur du rejet",
    "Pourquoi tu vis selon les attentes des autres pas les tiennes",
    "Pourquoi tu te sens coupable même quand tu n'as rien fait de mal",
    "Pourquoi le couple le plus stable s'est rencontré par hasard",
    "Pourquoi tu changes de personnalité selon avec qui tu es",
    "Pourquoi le besoin d'approbation est un piège sans fin",
    "Pourquoi tu confonds amour et dépendance affective",
    "Pourquoi tu oublies les bons moments en couple plus vite que les mauvais",
    "Pourquoi l'absence fait plus d'effet que la présence",
    "Pourquoi tu interprètes le silence comme un rejet",
    "Pourquoi tu tests les gens sans t'en rendre compte",
    "Pourquoi tu préfères être blessé que seul",
    "Pourquoi tu donnes toujours plus que tu ne reçois",
    "Pourquoi tu confonds attention et amour",
    "Pourquoi ton corps révèle quand tu mens même si tu es silencieux",
    "Pourquoi ton visage trahit tes émotions même si tu le caches",
    "Pourquoi tes mains trahissent ton stress en silence",
    "Pourquoi tu rougis quand tu mens sans pouvoir le contrôler",
    "Pourquoi ta posture change comment les gens te voient",
    "Pourquoi les yeux ne mentent jamais même quand la bouche ment",
    "Pourquoi le silence met les gens mal à l'aise qu'ils avouent",
    "Pourquoi ton corps copie les gestes des autres sans que tu le saches",
    "Pourquoi la distance physique révèle tes sentiments",
    "Pourquoi tu serres la main faiblement pour dominer sans le savoir",
    "Pourquoi tu mens 200 fois par jour sans le compter",
    "Pourquoi tu fais semblant d'écouter mais tu attends juste ton tour",
    "Pourquoi tu te sens coupable sans avoir fait quoi que ce soit",
    "Pourquoi tu parles de toi soit trop peu soit trop",
    "Pourquoi tu attends la permission pour être heureux",
    "Pourquoi les 7 premières secondes déterminent tout",
    "Pourquoi tu ne changes pas d'avis quand on te prouve que tu as tort",
    "Pourquoi ton cerveau oublie 90% de ce qu'on te dit",
    "Pourquoi la voix grave inspire plus de confiance",
    "Pourquoi tu sens les mensonges dans la voix des autres",
    "Pourquoi les gens changent de voix quand ils mentent",
    "Pourquoi le rythme de ta marche révèle ton humeur",
    "Pourquoi tu mords l'intérieur de ta joue quand tu es stressé",
    "Pourquoi tu te touches le visage quand tu mens",
    "Pourquoi le regard fuyant est un signe de manipulation",
    "Pourquoi les gens qui mentent parlent plus que nécessaire",
    "Pourquoi le ton de voix influence plus que les mots",
    "Pourquoi tu crois les gens souriants plus facilement",
    "Pourquoi le contact visuel excessif est un signe de contrôle",
    "Pourquoi tu inclines la tête quand tu es attiré",
    "Pourquoi les mains ouvertes inspirent plus de confiance que les poings fermés",
    "Pourquoi tu évites le regard quand tu es embarrassé",
    "Pourquoi le silence de 3 secondes force les gens à avouer",
    "Pourquoi tu bégayes quand tu mens sous pression",
    "Pourquoi les gens se penchent vers toi quand ils sont intéressés",
    "Pourquoi la distance entre deux personnes révèle leur relation",
    "Pourquoi tu respires plus vite quand tu es stressé",
    "Pourquoi le stress se lit sur tes épaules avant ta bouche",
    "Pourquoi les micro-expositions disent plus que les mots",
    "Pourquoi les gens qui se mentent à eux-mêmes mentent aux autres",
    "Pourquoi la fatigue rend ton visage plus honnête",
    "Pourquoi tu roules les yeux sans t'en rendre compte",
    "Pourquoi tu serres les dents la nuit sans le savoir",
    "Pourquoi le stress te fait mâcher plus vite",
    "Pourquoi les gens qui évitent le contact ont quelque chose à cacher",
    "Pourquoi le rire nerveux est un signe de manipulation",
    "Pourquoi tu transpires quand tu mens même à froid",
    "Pourquoi les mains froides révèlent un stress chronique",
    "Pourquoi ton corps réagit avant ton cerveau",
    "Pourquoi les algorithmes contrôlent ce que tu penses",
    "Pourquoi les réseaux sociaux exploitent les failles de ton cerveau",
    "Pourquoi l'école t'enseigne l'obéissance pas la pensée critique",
    "Pourquoi la publicité utilise des couleurs pour te manipuler",
    "Pourquoi les supermarchés sont conçus pour te faire dépenser plus",
    "Pourquoi les médias choisissent les informations que tu reçois",
    "Pourquoi le pouvoir attire les gens les moins adaptés",
    "Pourquoi les élections sont influencées par la météo",
    "Pourquoi Napoléon utilisait cette technique de contrôle",
    "Pourquoi les Romains utilisaient le pain et les jeux pour contrôler",
    "Pourquoi la justice n'est pas aveugle elle est biaisée",
    "Pourquoi tu suis la majorité même quand elle a tort",
    "Pourquoi la propagande utilise les mêmes techniques depuis 100 ans",
    "Pourquoi les superstitions existent dans 99% des cultures",
    "Pourquoi les gens obéissent à un uniforme sans réfléchir",
    "Pourquoi la publicité au son augmente les ventes de 30%",
    "Pourquoi les magasins sentent bon pour te faire acheter plus",
    "Pourquoi les journaux mettent les mauvaises nouvelles en première",
    "Pourquoi les gens partagent des fake news sans vérifier",
    "Pourquoi les traditions absurdes persistent des siècles",
    "Pourquoi tu fais confiance à un avis en ligne plus qu'à un ami",
    "Pourquoi les influenceurs te manipulent sans que tu le voies",
    "Pourquoi les publicités répètent pour mieux te convaincre",
    "Pourquoi les primes limitées créent un besoin fictif",
    "Pourquoi les gens défendent une opinion fausse quand ils la répètent",
    "Pourquoi la musique de supermarché te fait marcher plus lentement",
    "Pourquoi le design des réseaux sociaux est une addiction calculée",
    "Pourquoi les notifications rouges sont plus attirantes",
    "Pourquoi les gens préfèrent être mentorés que libres",
    "Pourquoi la normalisation du sacrifice est un outil de contrôle",
    "Pourquoi les dictateurs commencent toujours par l'éducation",
    "Pourquoi la peur est le meilleur outil de gouvernance",
    "Pourquoi les gens acceptent des inégalités qu'ils pourraient changer",
    "Pourquoi les médias de masse créent des boucles de peur",
    "Pourquoi le format des bulletins d'info est conçu pour anesthésier",
    "Pourquoi tu ne sais pas ce qui se passe au-delà de ton flux",
    "Pourquoi lesgens partagent plus la colère que la joie",
    "Pourquoi la propagande moderne ressemble à du divertissement",
    "Pourquoi tu détestes les gens qui pensent différemment de toi",
    "Pourquoi la technologie nous isole plus qu'elle ne nous connecte",
    "Pourquoi la peur du rejet est plus forte que la peur de la mort",
    "Pourquoi le conflit te fait plus peur que la solitude",
    "Pourquoi tu te sens coupable même quand tu n'as rien fait de mal",
    "Pourquoi tu ne te donnes pas le droit d'être heureux",
    "Pourquoi tu as peur de réussir autant que d'échouer",
    "Pourquoi tu préfères la douleur connue au bonheur inconnu",
    "Pourquoi tu utilises le travail pour fuir tes émotions",
    "Pourquoi tu te sous-estimes sans raison objective",
    "Pourquoi tu as peur du jugement même de parfaits inconnus",
    "Pourquoi tu préfères souffrir en silence que demander de l'aide",
    "Pourquoi tu n'oses pas dire la vérité par peur du rejet",
    "Pourquoi tu vis selon les attentes des autres pas les tiennes",
    "Pourquoi le simple fait d'être vu te met mal à l'aise",
    "Pourquoi tu te sens responsable du bonheur de tout le monde",
    "Pourquoi tu évites les镜子 par peur de te voir tel que tu es",
    "Pourquoi la joie te met mal à l'aise après une période difficile",
    "Pourquoi tu refoules tes émotions au lieu de les vivre",
    "Pourquoi tu ris quand tu devrais pleurer",
    "Pourquoi tu pleures quand tu devrais être en colère",
    "Pourquoi tu ressens de la honte sans raison apparente",
    "Pourquoi tu confonds paix et absence de conflit",
    "Pourquoi tu attends d'être malheureux pour demander de l'aide",
    "Pourquoi tu penses que tu ne mérites pas le bonheur",
    "Pourquoi tu repousses les bonnes nouvelles par méfiance",
    "Pourquoi tu sabotes tes propres réussites",
    "Pourquoi tu préfères le chaos à l'incertitude",
    "Pourquoi tu confonds passion et dépendance affective",
    "Pourquoi le bonheur te fait peur quand tu as longtemps souffert",
    "Pourquoi tu cherches inconsciemment des raisons d'être malheureux",
    "Pourquoi tu confonds courage et insouciance",
    "Pourquoi tu es accro à ton téléphone sans le savoir",
    "Pourquoi tu vérifies ton téléphone 100 fois par jour",
    "Pourquoi les réseaux sociaux sont conçus comme une drogue",
    "Pourquoi tu scrolles 3 heures sans t'en rendre compte",
    "Pourquoi tu te sens anxious quand ton téléphone est loin",
    "Pourquoi la dopamine te pousse à faire des choses stupides",
    "Pourquoi tu manges pour tes émotions pas pour ta faim",
    "Pourquoi tu procrastines par peur de réussir",
    "Pourquoi tu achètes des choses pour combler un vide",
    "Pourquoi tu restes éveillé par peur de dormir",
    "Pourquoi la notification rouge déclenche ton instinct de survie",
    "Pourquoi tu vérifies les réseaux sociaux dès le réveil",
    "Pourquoi tu scrolles même quand tu as dit d'arrêter",
    "Pourquoi tu achètes des choses que tu n'as pas besoin",
    "Pourquoi tu manges même quand tu n'as plus faim",
    "Pourquoi tu restes debout même épuisé",
    "Pourquoi tu évites le silence comme la peste",
    "Pourquoi tu remplaces un tic par un autre",
    "Pourquoi tu procrastines les choses qui te rendent heureux",
    "Pourquoi tu te punis inconsciemment quand ça va bien",
]


# -----------------------------------------------
# Dynamic topic generation: when the static pool
# runs low, call Groq LLM to generate fresh topics
# so the channel never repeats.
# -----------------------------------------------

_DYNAMIC_TOPIC_CACHE: list = []  # filled on first shortfall


def _generate_dynamic_topics(count: int = 50) -> list[str]:
    """Use the same Groq LLM the script generator uses to mint fresh,
    unique topic strings that fit the channel's dark-body-science niche.

    Called lazily — only when the static pool + trend pool are exhausted
    or fully excluded.  Returns an empty list on any failure so the
    pipeline gracefully falls back to the static pool.
    """
    try:
        import os

        from groq import Groq

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return []
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            # Env-driven (2026-08-12): llama-3.1-8b-instant retires 2026-08-16.
            model=os.environ.get("GROQ_MODEL") or "openai/gpt-oss-120b",
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Generate exactly {count} unique, curiosity-driven YouTube Shorts "
                        "topic titles about the human body, brain, health, and science. "
                        "Each must be under 60 characters, sound like a real person talking "
                        "(use 'Your' or 'You'), and NOT use clickbait phrases like "
                        "'doctors don't want', 'shocking', 'you won't believe', or "
                        "'this will blow your mind'. Return ONLY a JSON array of strings."
                    ),
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.9,
            max_tokens=2000,
        )
        import json

        data = json.loads(resp.choices[0].message.content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return v
        return []
    except Exception as e:
        logger.warning(f"Dynamic topic generation failed: {e}")
        return []


# ============================================
# 2. HOOK FORMULAS — DARK PSYCHOLOGY (French)
# ============================================
HOOK_FORMULAS = [
    "Quelque chose dans ton cerveau te manipulate et tu ne le vois pas.",
    "Tu fais ça tous les jours sans jamais te poser la question.",
    "Personne ne t'a jamais dit ce qui se passe vraiment.",
    "Ton corps te trahit et tu ne peux pas le contrôler.",
    "C'est la partie de {topic} qu'on ne t'explique jamais.",
    "Les psychologues le savent depuis longtemps.",
    "Ton cerveau cache ça de toi depuis toujours.",
    "C'est pour ça que {topic} est si troublant quand tu comprends.",
    "La plupart des gens ne le savent jamais.",
    "Il y a une raison pour laquelles on n'en parle pas.",
    "C'est ce qui se passe vraiment quand {topic}.",
    "Chaque fois que {topic}, ton cerveau essaie de te dire quelque chose.",
    "La psychologie derrière {topic} est plus étrange que la fiction.",
    "Voilà la vraie raison de {topic}.",
    "Ce qui se passe quand {topic} est fascinant.",
    "Ton cerveau fait quelque chose d'insensé pendant {topic}.",
    "La vérité sur {topic} est plus intéressante que tu ne le crois.",
    "La plupart des gens ignorent ça sur {topic}.",
    "Ce fait sur {topic} va changer ta vision.",
    "Ce qui se passe vraiment pendant {topic} est surprenant.",
    "Ton cerveau a une réponse instinctive à {topic}.",
    "La psychologie de {topic} commence à être comprise.",
    "Voici ce qu'on ne t'explique jamais sur {topic}.",
    "Ce que ton cerveau fait pendant {topic} est incroyable.",
    "La raison de {topic} est plus complexe que tu ne crois.",
    "Ton cerveau te ment sur {topic} depuis toujours.",
    "Il y a un signal caché dans {topic} que tu ne remarques pas.",
    "Les gens te manipulent avec {topic} sans que tu le voies.",
    "Ce que {topic} révèle sur toi est plus sombre que tu ne crois.",
    "Tu crois comprendre {topic} mais tu te trompes lourdement.",
]

# ============================================
# 3. TRANSITION HOOKS — DARK PSYCHOLOGY (French)
# ============================================
TRANSITION_HOOKS = [
    "mais c'est pas tout...",
    "et c'est là que ça devient flippant...",
    "voilà ce qu'on ne te dit pas...",
    "et c'est la partie que personne ne montre...",
    "mais le vrai problème c'est ailleurs...",
    "et c'est là que ton cerveau te piège...",
    "sauf que...",
    "et c'est ça qui est dingue...",
    "mais le plus troublant c'est...",
    "et ça change tout...",
    "mais voici le piège...",
    "et c'est là que ça devient sombre...",
    "mais le mécanisme est pire que tu ne crois...",
    "et personne n'en parle...",
    "mais la vérité est pire...",
    "et c'est pour ça que personne ne le voit...",
    "sauf que ton cerveau sabote tout...",
    "et c'est exactement ce qu'ils veulent...",
    "mais le cerveau a un plan B...",
    "et ça va te choquer...",
]

# ============================================
# 4. PAIN POINTS — DARK PSYCHOLOGY
# ============================================
PAIN_POINTS = [
    "Ne comprend pas pourquoi il dit toujours oui",
    "Se sent manipulé mais ne peut pas prouver",
    "Repense constamment à des moments gênants",
    "Ne sait pas pourquoi il attire les mauvaises personnes",
    "Se sent vide même quand tout va bien",
    "Fait semblant d'aller bien mais souffre en silence",
    "Ne comprend pas pourquoi il procrastine",
    "Se compare tout le temps aux autres",
    "A peur du rejet plus que tout",
    "Ne sait pas dire non",
    "Se sent coupable sans raison",
    "Ne comprend pas ses propres émotions",
    "Vit selon les attentes des autres",
    "Se sent incompris même par ses proches",
    "Ne comprend pas pourquoi les gens mentent",
]

# ============================================
# 5. CTAS — NATURAL, NO ENGAGEMENT BAIT
# YouTube 2026 penalizes: "like if", "comment 🤯",
# "tag someone", "smash like", etc.
# These sound like a real person ending a conversation.
# ============================================
CTAS = [
    "Follow for more facts like this.",
    "More science that surprises you — follow along.",
    "See you in the next one.",
    "Follow if you want to understand your body better.",
    "More coming — follow so you don't miss it.",
    "If this surprised you, there's more where that came from.",
    "Follow for the next one — it's just as wild.",
    "Share this with someone who loves random facts.",
    "Follow for daily body science.",
    "Bookmark this for later — you'll want to remember it.",
    "Want more? Follow for the next deep dive.",
    "This channel explains the stuff nobody else does — follow.",
    "Follow along — new facts every day.",
    "Save this one — it comes up in conversation.",
    "Follow for the next body mystery explained.",
]

# ============================================
# 6. CATEGORY TAGS — DARK PSYCHOLOGY (French)
# ============================================
CATEGORY_TAGS = {
    "Psychology": [
        "psychologie",
        "psychologie sombre",
        "science du comportement",
        "cerveau",
        "biais cognitifs",
        "manipulation",
        "comportement humain",
        "mental",
        "psychologie sociale",
        "influence",
        "pouvoir",
        "séduction",
    ],
    "Relations": [
        "relations",
        "amour",
        "couple",
        "attachement",
        "toxicité",
        "manipulation affective",
        "sentiments",
        "confiance",
        "jalousie",
        "rupture",
        "relations humaines",
        "psychologie amoureuse",
    ],
    "Mystery": [
        "mystère",
        "secrets",
        "inexpliqué",
        "comportement caché",
        "vérité cachée",
        "ce qu'on ne dit pas",
        "réalité",
        "illusion",
        "inconscient",
        "vérité",
        "révélation",
        "ce que tu ignores",
    ],
    "Social": [
        "société",
        "social",
        "mœurs",
        "culture",
        "sociologie",
        "comportement social",
        "normes",
        "pression sociale",
        "obéissance",
        "propagande",
        "médias",
        "réseaux sociaux",
    ],
}

# ============================================
# 7. BASE TAGS — DARK PSYCHOLOGY (French)
# ============================================
BASE_TAGS = [
    "psychologie",
    "shorts",
    "dark",
    "psychologie sombre",
    "manipulation",
    "secrets",
    "comportement",
    "viral",
    "mystère",
    "intéressant",
    "éducation",
    "curiosité",
    "savoir",
    "apprendre",
    "révélation",
]

# ============================================
# 8. CONSTANTS
# ============================================
TARGET_WORD_RANGE = (90, 120)
MAX_TAGS = 15
MAX_TITLE_LENGTH = 55
SCENES_PER_SCRIPT = 8  # Dark Psychology 20-30 second series policy

# ============================================
# 9. MEDICAL RED FLAGS
# ============================================
_MEDICAL_ADVICE_RED_FLAGS = [
    "cure",
    "diagnose",
    "you have",
    "stop taking",
    "don't need a doctor",
    "instead of medication",
    "guaranteed to heal",
    "definitely means you have",
    "you should",
    "you must",
    "never go to the doctor",
    "ignore your doctor",
    "this is the only cure",
    "better than medicine",
    "replace your medication",
]

# ============================================
# 10. RETENTION-OPTIMIZED PROMPT GENERATION
# ============================================


def get_script_prompt_for_niche(
    topic: str,
    hook_preference: str | None = None,
) -> str:
    """Compatibility wrapper for the unified script policy.

    Historically this module built a second, conflicting prompt (80–115 words,
    different hook limits and a forced dark tone). Keep the public function for
    callers, but delegate to ``script_generator`` so generation and validation
    always share exactly one contract.
    """
    from script_generator import _default_prompt

    return _default_prompt(topic)


def get_random_transition_hook() -> str:
    """Get a random transition hook for scene endings. BLIND (no measured
    input) — logs BLIND-PICK so any production caller becomes visible."""
    _log_blind_pick_warning("get_random_transition_hook")
    return random.choice(TRANSITION_HOOKS)


def get_transition_hooks(count: int = 3) -> list[str]:
    """Get multiple transition hooks"""
    return random.sample(TRANSITION_HOOKS, min(count, len(TRANSITION_HOOKS)))


# ============================================
# 11. CORE FUNCTIONS
# ============================================


def get_random_topic(exclude: list[str] | None = None) -> str:
    """
    Picks a topic for the next video.

    Priority:
    1. Live trend-research topics (60% chance when available)
    2. Static DARK_TOPICS pool (fallback)
    3. Dynamic LLM-generated topics (when static pool exhausted)
    4. Skips recently used topics from exclude list
    """
    global _DYNAMIC_TOPIC_CACHE
    exclude_set = {t.strip().lower() for t in (exclude or []) if t}
    logger.debug(f"Excluding {len(exclude_set)} recent topics")

    # Try to get trending topics
    trending = []
    try:
        from trend_research import fetch_trending_topics

        trending = fetch_trending_topics()
        logger.debug(f"Fetched {len(trending)} trending topics")
    except ImportError:
        logger.debug("Trend research module not available")
    except Exception as e:
        logger.warning(f"Trend research failed: {e}")

    trend_candidates = [t for t in trending if t.strip().lower() not in exclude_set]

    # 🚀 BRAIN UPGRADE: Apply learned weights to candidates
    try:
        from autonomous_brain import apply_learned_weights_to_topics

        trend_candidates = apply_learned_weights_to_topics(trend_candidates)
    except Exception:
        pass

    if trend_candidates and random.random() < 0.6:
        chosen = random.choice(trend_candidates)
        logger.info(f"Selected trending topic: {chosen}")
        return chosen

    # Fallback to static pool
    static_candidates = [t for t in DARK_TOPICS if t.strip().lower() not in exclude_set]

    if static_candidates:
        chosen = random.choice(static_candidates)
        logger.info(f"Selected static topic: {chosen}")
        return chosen

    # Static pool exhausted → try dynamic LLM generation
    if not _DYNAMIC_TOPIC_CACHE:
        logger.info("Static topic pool exhausted — generating fresh topics via LLM...")
        _DYNAMIC_TOPIC_CACHE = _generate_dynamic_topics(50)
        if _DYNAMIC_TOPIC_CACHE:
            logger.info(f"Generated {len(_DYNAMIC_TOPIC_CACHE)} fresh topics from LLM")

    dynamic_candidates = [t for t in _DYNAMIC_TOPIC_CACHE if t.strip().lower() not in exclude_set]
    if dynamic_candidates:
        chosen = dynamic_candidates.pop(random.randrange(len(dynamic_candidates)))
        logger.info(f"Selected dynamic topic: {chosen}")
        return chosen

    # Last resort: allow a repeat from static pool
    logger.warning("All topic sources exhausted — allowing repeat from static pool")
    return random.choice(DARK_TOPICS)


def get_topic_category(topic: str) -> str:
    """Categorizes a topic into Brain, Body, Mystery, or Health."""
    topic_lower = topic.lower()

    brain_keywords = ["brain", "mind", "sleep", "nerve", "psych", "memory", "thought", "conscious"]
    body_keywords = ["heart", "blood", "lung", "kidney", "bone", "organ", "muscle", "vein", "artery"]
    mystery_keywords = ["scary", "secret", "dark", "mystery", "hidden", "unknown", "creepy", "weird"]

    def _has_word(words):
        return any(re.search(r"\b" + re.escape(w), topic_lower) for w in words)

    if _has_word(brain_keywords):
        return "Brain"
    elif _has_word(mystery_keywords):
        return "Mystery"
    elif _has_word(body_keywords):
        return "Body"
    else:
        return "Body"  # Default


def get_seo_tags(topic: str, category: str = "Body") -> list[str]:
    """Returns YouTube-optimized tags (max 15)."""
    _FR_STOPWORDS = {
        "dans",
        "avec",
        "pour",
        "quand",
        "vous",
        "votre",
        "vos",
        "notre",
        "est",
        "sont",
        "être",
        "avoir",
        "cela",
        "peut",
        "plus",
        "très",
        "tout",
        "toute",
        "entre",
        "leur",
        "leurs",
        "comme",
        "aussi",
        "sans",
        "sous",
        "chez",
        "alors",
        "encore",
        "faire",
        "fait",
        "avant",
        "après",
        "pendant",
        "toujours",
        "jamais",
        "même",
        "cette",
        "quoi",
        "your",
        "this",
        "that",
        "what",
        "when",
    }
    topic_words = [w.strip(",.?!:;'’«»\"()") for w in topic.lower().split()]
    topic_words = [w for w in topic_words if len(w) > 3 and w not in _FR_STOPWORDS]
    tags = topic_words[:5]
    tags.extend(CATEGORY_TAGS.get(category, []))
    related_phrases = [
        "corps humain",
        "faits scientifiques",
        "science expliquée",
        "secrets du corps",
        "faits mystérieux",
        "anatomie humaine",
    ]
    tags.extend(related_phrases)
    tags.extend(BASE_TAGS)

    seen = set()
    result = []
    for tag in tags:
        clean = tag.strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(tag)
        if len(result) >= MAX_TAGS:
            break

    return result


def generate_seo_tags(topic: str, category: str = "Body", title: str = "") -> list[str]:
    """Wrapper for get_seo_tags for compatibility."""
    return get_seo_tags(topic, category)


def validate_script_for_medical_accuracy(script_data: dict) -> dict:
    """Validates that script doesn't contain medical advice."""
    voiceover = script_data.get("voiceover", "")
    if not voiceover:
        voiceover = " ".join(
            [s.get("caption", "") for s in script_data.get("scenes", []) if isinstance(s, dict)]
        )

    lowered = voiceover.lower()
    flags = [phrase for phrase in _MEDICAL_ADVICE_RED_FLAGS if phrase in lowered]

    return {"valid": len(flags) == 0, "flags": flags, "has_red_flags": len(flags) > 0}


def auto_add_disclaimer(script_data: dict) -> dict:
    """Adds medical disclaimer to script."""
    disclaimer = "Cette vidéo est éducative et ne remplace pas un avis médical. En cas de question de santé, consultez un professionnel qualifié."

    script_data["cta"] = (script_data.get("cta", "") + " " + disclaimer).strip()

    if "description" in script_data:
        script_data["description"] = (script_data["description"] + " " + disclaimer).strip()

    script_data["disclaimer_added"] = True
    logger.info("Added medical disclaimer to script")
    return script_data


# Emoji chosen by matching actual topic keywords
_TOPIC_EMOJI_MAP = [
    (["bone", "bones", "skeleton"], "🦴"),
    (["leg", "legs", "knee", "knees"], "🦵"),
    (["ear", "ears", "hearing", "sound"], "👂"),
    (["heart", "blood", "pulse", "heartbeat"], "🫀"),
    (["immune", "microbiome", "bacteria", "germ", "germs", "virus"], "🦠"),
    (["fingerprint", "fingerprints", "finger", "fingers"], "🫆"),
    (["cold", "chill", "chills", "temperature", "fever"], "🥶"),
    (["eye", "eyes", "see", "sight", "blind spot"], "👁️"),
    (["muscle", "muscles", "strength", "exercise"], "💪"),
    (["sleep", "sleeping", "night", "nightmare", "nightmares"], "😴"),
    (["brain", "mind", "memory", "thought"], "🧠"),
]

_EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F1E6-\U0001F1FF]+\s*")


def _pick_topic_emoji(topic: str) -> str:
    """Pick the most relevant emoji for a topic."""
    topic_lower = topic.lower()
    for keywords, emoji in _TOPIC_EMOJI_MAP:
        if any(re.search(r"\b" + re.escape(kw) + r"\b", topic_lower) for kw in keywords):
            return emoji

    category = get_topic_category(topic)
    return {"Brain": "🧠", "Body": "🫀", "Mystery": "👁️", "Health": "🦠"}.get(category, "🫀")


def _make_seo_title(title: str, topic: str) -> str:
    """Enhances title for SEO while keeping under 55 chars."""
    clean_title = _EMOJI_PATTERN.sub("", title, count=1).strip()

    power_words = [
        "secret",
        "nobody",
        "never",
        "actually",
        "dark",
        "scary",
        "real",
        "hidden",
        "warning",
        "shock",
        "fact",
        "truth",
    ]
    if any(pw in clean_title.lower() for pw in power_words):
        return clean_title[:MAX_TITLE_LENGTH]

    emoji = _pick_topic_emoji(topic)

    enhanced = f"{clean_title} {emoji}"
    if len(enhanced) <= MAX_TITLE_LENGTH:
        return enhanced

    return clean_title[:MAX_TITLE_LENGTH]


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------


def make_seo_title(title: str, topic: str) -> str:
    """Enhance a video title for SEO (emoji + power-word detection).

    Public wrapper around the internal ``_make_seo_title``.
    """
    return _make_seo_title(title, topic)


# ============================================
# 12. UTILITY FUNCTIONS
# ============================================


def _log_blind_pick_warning(name: str) -> None:
    """These legacy helpers pick a template with random.choice and NO
    measured-outcome input. Post truth-gate doctrine (2026-08-12): nothing in
    the pipeline may be blind. Production paths (script_generator prompts,
    trend_fetcher demand queue) never call these — they exist for backwards
    compatibility only. Any caller gets a loud log so the blindness is
    observable, not silent."""
    import logging

    logging.getLogger(__name__).warning(
        "BLIND-PICK: %s uses unmeasured random templates. Production must "
        "prefer measured sources (demand queue / truth gate / bandit). "
        "If this log appears in main runs, wire the caller to intelligence "
        "instead.",
        name,
    )


def get_random_hook(topic: str | None = None) -> str:
    """Get a random hook formula, optionally with topic."""
    _log_blind_pick_warning("get_random_hook")
    hook = random.choice(HOOK_FORMULAS)
    if topic and "{topic}" in hook:
        hook = hook.format(topic=topic)
    return hook


def get_random_pain_point() -> str:
    """Get a random pain point."""
    _log_blind_pick_warning("get_random_pain_point")
    return random.choice(PAIN_POINTS)


def get_random_cta() -> str:
    """Get a random CTA."""
    _log_blind_pick_warning("get_random_cta")
    return random.choice(CTAS)


def get_category_tags(category: str) -> list[str]:
    """Get tags for a specific category."""
    return CATEGORY_TAGS.get(category, CATEGORY_TAGS["Body"])


def get_scene_count() -> int:
    """Get the optimal number of scenes for retention."""
    return SCENES_PER_SCRIPT


# ============================================
# 13. RETENTION ANALYSIS FUNCTIONS
# ============================================


def analyze_retention_potential(script_data: dict) -> dict:
    """Analyzes script for retention potential."""
    scenes = script_data.get("scenes", [])
    score = 0
    suggestions = []

    if len(scenes) == SCENES_PER_SCRIPT:
        score += 20
    else:
        suggestions.append(f"Optimal scene count is {SCENES_PER_SCRIPT}, currently {len(scenes)}")

    cliffhanger_count = 0
    for scene in scenes:
        caption = scene.get("caption", "")
        if any(word in caption.lower() for word in ["...", "but", "however", "yet", "still"]):
            cliffhanger_count += 1

    cliffhanger_ratio = cliffhanger_count / len(scenes) if scenes else 0
    if 1 <= cliffhanger_count <= 2:
        score += 30
    elif cliffhanger_count > 2:
        suggestions.append(f"Too many forced cliffhangers ({cliffhanger_count}); use at most two")
    else:
        suggestions.append("Add one natural open loop after the hook")

    you_count = 0
    for scene in scenes:
        caption = scene.get("caption", "")
        you_count += caption.lower().count("you")

    if you_count >= len(scenes) * 2:
        score += 25
    else:
        suggestions.append("Use more 'YOU' language for personal connection")

    visual_quality = 0
    for scene in scenes:
        visual = scene.get("visual", "")
        if any(word in visual.lower() for word in ["cinematic", "macro", "close", "dark", "dramatic"]):
            visual_quality += 1

    if visual_quality >= len(scenes) * 0.6:
        score += 25
    else:
        suggestions.append("Make visuals more CINEMATIC and DYNAMIC")

    return {
        "retention_score": min(100, score),
        "suggestions": suggestions,
        "cliffhanger_ratio": cliffhanger_ratio,
        "you_count": you_count,
        "visual_quality": visual_quality / len(scenes) if scenes else 0,
    }


# ============================================
# 14. MAIN EXECUTION
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("RETENTION-OPTIMIZED NICHE STRATEGY TEST")
    print(f"Static topic pool: {len(DARK_TOPICS)} topics")
    print("=" * 60)

    print("\n1. Topic Selection:")
    for _i in range(3):
        topic = get_random_topic()
        print(f"   - {topic}")

    print("\n2. Hooks (no clickbait):")
    for _i in range(3):
        print(f"   - {get_random_hook('your brain')}")

    print("\n3. CTAs (natural, no engagement bait):")
    for _i in range(3):
        print(f"   - {get_random_cta()}")

    print("\n" + "=" * 60)
    print("✅ NICHE STRATEGY MODULE READY!")
    print("=" * 60)
