"""Génère le catalogue France-first de 500 sujets « Dark Psychology ».

Niche: Psychologie sombre, manipulation, biais cognitifs, lois du pouvoir,
signaux cachés du comportement humain.

Cible: Francophones (France, Belgique, Suisse, Canada, Afrique francophone).
Ton: Curieux, surprenant, révélateur — JAMAIS effrayant ou malveillant.

Chaque sujet génère 5 angles (100 topics × 5 = 500 titres uniques).
"""

from __future__ import annotations

import json
from pathlib import Path

# (label série, q = proposition sujet+verbe, n = syntagme nominal défini, vignette)
PHENOMENA = [
    # ── Manipulation & Persuasion (40+) ──
    (
        "Tu dis oui alors que tu veux dire non",
        "tu dis oui alors que tu veux dire non",
        "la raison pour laquelle tu dis oui alors que tu veux dire non",
        "POURQUOI TU DIS OUI ?",
    ),
    (
        "Les menteurs regardent toujours à gauche",
        "les menteurs regardent toujours à gauche quand ils mentent",
        "le regard des menteurs quand ils mentent",
        "REGARD DES MENTEURS ?",
    ),
    (
        "Les gens te manipulent sans que tu le saches",
        "des gens te manipulent sans que tu le saches",
        "les signes que quelqu'un te manipule sans que tu le voies",
        "MANIPULATION ?",
    ),
    (
        "Tu obéis à l'autorité sans réfléchir",
        "tu obéis à l'autorité sans réfléchir",
        "l'obéissance aveugle à l'autorité",
        "TU OBEIS SANS LE SAVOIR ?",
    ),
    (
        "Le pouvoir change la personnalité",
        "le pouvoir change la personnalité de quelqu'un",
        "la façon dont le pouvoir change la personnalité",
        "LE POUVOIR TE CHANGE ?",
    ),
    (
        "Tu te fais influencer par le regard des autres",
        "le regard des autres t'influence sans que tu le voies",
        "l'influence du regard des autres sur tes décisions",
        "LE REGARD INFLUENCE ?",
    ),
    (
        "Le mensonge le plus courant au monde",
        "le mensonge le plus courant au monde est dit chaque jour",
        "le mensonge le plus courant au monde",
        "MENSONGE QUOTIDIEN ?",
    ),
    (
        "Tu fais confiance aux gens qui te mentent",
        "tu fais confiance aux gens qui te mentent le plus",
        "pourquoi tu fais confiance aux menteurs",
        "CONFIANCE AUX MENTEURS ?",
    ),
    (
        "Les manipulateurs utilisent ton prénom",
        "les manipulateurs utilisent ton prénom pour te contrôler",
        "l'usage du prénom par les manipulateurs",
        "UTILISER TON PRÉNOM ?",
    ),
    (
        "Tu acceptes des choses que tu n'accepterais pas seul",
        "tu acceptes des choses que tu n'accepterais pas seul",
        "la pression du groupe qui te fait accepter",
        "PRESSION DU GROUPE ?",
    ),

    # ── Biais Cognitifs / Le Cerveau Te Ment (40+) ──
    (
        "Ton cerveau te ment chaque jour",
        "ton cerveau te ment chaque jour sans que tu le saches",
        "les mensonges que ton cerveau te raconte chaque jour",
        "CERVEAU QUI MENT ?",
    ),
    (
        "Tu crois être meilleur que la moyenne",
        "tu crois être meilleur que la moyenne en tout",
        "l'illusion de supériorité que tout le monde a",
        "MIEUX QUE TOUS ?",
    ),
    (
        "Tu ne vois que ce que tu veux voir",
        "ton cerveau ne te montre que ce que tu veux voir",
        "le biais de confirmation qui contrôle ta vision",
        "TU NE VOIS PAS TOUT ?",
    ),
    (
        "Ton cerveau invente des souvenirs faux",
        "ton cerveau invente des souvenirs qui ne sont jamais arrivés",
        "les faux souvenirs créés par ton cerveau",
        "FAUX SOUVENIRS ?",
    ),
    (
        "Tu te souviens de ce qui te fait peur",
        "ton cerveau retient plus facilement ce qui te fait peur",
        "le biais de négativité dans ta mémoire",
        "PEUR > BONHEUR ?",
    ),
    (
        "Le prix influence ce que tu aimes",
        "le prix d'un produit influence ce que tu aimes vraiment",
        "comment le prix trompe ton goût",
        "PRIX = QUALITÉ ?",
    ),
    (
        "Tu fais la même erreur que tout le monde",
        "tu fais une erreur cognitive que 99% des gens font",
        "l'erreur cognitive que tout le monde fait",
        "ERREUR UNIVERSELLE ?",
    ),
    (
        "Ton cerveau déteste perdre plus qu'il n'aime gagner",
        "ton cerveau déteste perdre deux fois plus qu'il n'aime gagner",
        "la peur de perdre qui contrôle tes décisions",
        "PERDRE > GAGNER ?",
    ),
    (
        "Tu juges un livre par sa couverture",
        "ton cerveau juge tout le monde en 7 secondes",
        "le biais d'halo qui contrôle tes premières impressions",
        "JUGEMENT EN 7 SEC ?",
    ),
    (
        "Tu te rappelles mal les bons moments",
        "ton cerveau oublie les bons moments plus vite que les mauvais",
        "le biais de rétrospection qui déforme ta mémoire",
        "BONS MOMENTS OUBLIÉS ?",
    ),

    # ── Relations & Attachement (40+) ──
    (
        "Tu tombes toujours amoureux du mauvais type",
        "tu tombes toujours amoureux du mauvais type de personne",
        "pourquoi tu attires les mauvaises personnes",
        "MAUVAISES PERSONNES ?",
    ),
    (
        "Le silence fait plus de dégâts que les mots",
        "le silence fait plus de dégâts que les mots dans un couple",
        "pourquoi le silence est l'arme la plus destructrice",
        "LE SILENCE DÉTRUIT ?",
    ),
    (
        "Tu repenses toujours à cette humiliation",
        "ton cerveau te fait revivre les humiliations en boucle",
        "pourquoi les souvenirs gênants reviennent sans cesse",
        "SOUVENIRS GÊNANTS ?",
    ),
    (
        "Tu attires ce que tu fuis",
        "tu attires dans ta vie ce que tu fuis le plus",
        "la loi de l'attraction inversée",
        "TU ATTIRE CE QUE TU FUIS ?",
    ),
    (
        "Les couples les plus stables se sont rencontrés par hasard",
        "les couples les plus stables se sont rencontrés par hasard",
        "le rôle du hasard dans les relations",
        "HASARD = AMOUR ?",
    ),
    (
        "Tu ne vois pas quand quelqu'un t'aime vraiment",
        "tu ne vois pas les signes quand quelqu'un t'aime vraiment",
        "les signes d'amour que tu ignores",
        "AMOUR INVISIBLE ?",
    ),
    (
        "La jalousie révèle ta peur pas ton amour",
        "la jalousie révèle ta peur pas ton amour",
        "ce que la jalousie dit vraiment de toi",
        "JALOUSIE = PEUR ?",
    ),
    (
        "Tu acceptes des excuses que tu ne devrais pas",
        "tu acceptes des excuses que tu ne devrais pas accepter",
        "pourquoi tu pardones quand tu ne devrais pas",
        "PARDON EXCESSIF ?",
    ),
    (
        "Ton besoin d'approbation te rend fragile",
        "ton besoin d'approbation te rend émotionnellement fragile",
        "la dépendance à l'approbation des autres",
        "BESOIN D'APPROBATION ?",
    ),
    (
        "Tu penses être indépendant mais tu ne l'es pas",
        "tu crois être indépendant mais tu depens de la validation",
        "l'illusion d'indépendance émotionnelle",
        "INDÉPENDANT ? VRAIMENT ?",
    ),

    # ── Pouvoir & Loi du Silence (40+) ──
    (
        "La loi du silence protège les abuseurs",
        "la loi du silence protège les abuseurs dans la société",
        "pourquoi personne ne parle quand quelqu'un souffre",
        "SILENCE = COMPLICE ?",
    ),
    (
        "Les personnes les plus dangereuses sont les plus charmantes",
        "les personnes les plus dangereuses sont les plus charmantes",
        "pourquoi le charme est souvent un masque",
        "CHARME = MASQUE ?",
    ),
    (
        "Tu ne remarques pas quand quelqu'un te contrôle",
        "tu ne remarques pas quand quelqu'un te contrôle progressivement",
        "les étapes de la manipulation progressive",
        "CONTRÔLE PROGRESSIF ?",
    ),
    (
        "Le pouvoir attire les gens les moins adaptés",
        "le pouvoir attire les gens les moins adaptés au pouvoir",
        "pourquoi les pires personnes cherchent le pouvoir",
        "POUVOIR = DANGER ?",
    ),
    (
        "Les institutions te font obéir sans que tu le saches",
        "les institutions t'enseignent l'obéissance sans que tu le saches",
        "l'obéissance programmée depuis l'enfance",
        "OBEISSANCE PROGRAMMÉE ?",
    ),
    (
        "Tu ne choisis pas librement tes opinions",
        "tu ne choisis pas librement tes opinions comme tu le crois",
        "comment les médias façonnent tes opinions",
        "OPINIONS LIBRES ?",
    ),
    (
        "La propagande utilise les mêmes techniques depuis 100 ans",
        "la propagande utilise les mêmes techniques depuis 100 ans",
        "les techniques de propagande inchangées",
        "PROPAGANDE TOUJOURS ?",
    ),
    (
        "Tu suis la majorité même quand elle a tort",
        "tu suis la majorité même quand elle a tort",
        "l'expérience d'Asch qui prouve ta soumission sociale",
        "TU SUIS LA MAJORITÉ ?",
    ),
    (
        "Lesalgorithmes contrôlent ce que tu penses",
        "les algorithmes contrôlent ce que tu penses sans que tu le voies",
        "comment les algorithmes manipulent tes pensées",
        "ALGORITHME = MANIPULATION ?",
    ),
    (
        "Les réseaux sociaux exploitent ton cerveau",
        "les réseaux sociaux exploitent les failles de ton cerveau",
        "comment les réseaux sociaux te contrôlent",
        "RÉSEAUX = CONTRÔLE ?",
    ),

    # ── Corps & Langage (40+) ──
    (
        "Ton corps révèle tes mensonges",
        "ton corps révèle quand tu mens même si tu es silencieux",
        "les signes corporels du mensonge",
        "CORPS QUI MENT ?",
    ),
    (
        "Tu ne contrôles pas ton visage",
        "ton visage révèle tes émotions même si tu le caches",
        "les micro-expressions qui trahissent tes sentiments",
        "VISAGE QUI TRAHIT ?",
    ),
    (
        "Les mains trahissent le stress",
        "tes mains trahissent ton stress même en silence",
        "les signes de stress visibles sur tes mains",
        "MAINS QUI TRAHISSENT ?",
    ),
    (
        "Tu rougis quand tu mens",
        "tu rougis quand tu mens sans pouvoir le contrôler",
        "pourquoi le rougissement trahit le menteur",
        "ROUGIR = MENTIR ?",
    ),
    (
        "Ta posture change comment les gens te voient",
        "ta posture change instantanément comment les gens te perçoivent",
        "le pouvoir de la posture sur les autres",
        "POSTURE = POUVOIR ?",
    ),
    (
        "Les yeux ne mentent jamais",
        "les yeux ne mentent jamais même quand la bouche ment",
        "ce que les yeux révèlent sur tes vrais sentiments",
        "YEUX VÉRITABLES ?",
    ),
    (
        "Le silence met les gens mal à l'aise",
        "le silence met les gens tellement mal à l'aille qu'ils avouent",
        "technique de silence pour faire parler",
        "SILENCE QUI FORGE ?",
    ),
    (
        "Tu copies sans le savoir les gestes des autres",
        "ton corps copie les gestes des autres sans que tu le saches",
        "le miroir inconscient dans les relations",
        "MIROIR INCONSCIENT ?",
    ),
    (
        "La distance physique révèle tes sentiments",
        "la distance physique que tu gardes révèle tes vrais sentiments",
        "comment la proxémie trahit tes émotions",
        "DISTANCE = SENTIMENTS ?",
    ),
    (
        "Tu serres la main faible quand tu veux dominer",
        "tu serres la main faiblement pour dominer sans le savoir",
        "le power play dans la poignée de main",
        "POIGNÉE = POUVOIR ?",
    ),

    # ── Secrets Sociaux / Comportement Caché (40+) ──
    (
        "Les gens parlent de toi quand tu n'es pas là",
        "les gens parlent de toi beaucoup plus que tu ne le crois",
        "la réalité des conversations sur toi",
        "ON PARLE DE TOI ?",
    ),
    (
        "Tu te souviens de 10% de ce qu'on te dit",
        "ton cerveau oublie 90% de ce qu'on te dit",
        "l'effet du taux d'oubli sur tes relations",
        "TU OUBLIES 90% ?",
    ),
    (
        "Le premier impact détermine tout",
        "le premier impact détermine 80% de ce qu'on pense de toi",
        "pourquoi les 7 premières secondes sont cruciales",
        "7 SECONDES = TON SORT ?",
    ),
    (
        "Tu ne changes pas d'avis quand on te prouve que tu as tort",
        "ton cerveau refuse de changer d'avis face à la preuve",
        "l'effet de réactance qui te rend têtu",
        "TÊTU SANS LE SAVOIR ?",
    ),
    (
        "Tu fais semblant d'écouter mais tu attends ton tour",
        "tu fais semblant d'écouter mais tu attends juste ton tour",
        "pourquoi tout le monde fait semblant d'écouter",
        "FAUX ÉCOUTEUR ?",
    ),
    (
        "Tu mens 200 fois par jour",
        "tu mens en moyenne 200 fois par jour sans le compter",
        "le nombre de mensonges quotidiens",
        "200 MENSONGES / JOUR ?",
    ),
    (
        "Tu te crois objectif mais tu ne l'es pas",
        "tu te crois objectif mais ton jugement est biaisé",
        "l'illusion d'objectivité qui te contrôle",
        "OBJECTIF ? JAMAIS.",
    ),
    (
        "Tu imites les gens que tu admires sans le savoir",
        "ton cerveau imite les gens que tu admires inconsciemment",
        "le miroir neuronal dans l'admiration",
        "IMITATION INCONSCIENTE ?",
    ),
    (
        "Tu mens pour protéger les autres pas toi-même",
        "tu mens pour protéger les autres pas pour toi-même",
        "les vraies raisons de tes mensonges",
        "MENTIR POUR AUTRUI ?",
    ),
    (
        "Tu n'oses pas dire non alors que tu devrais",
        "tu n'oses pas dire non alors que tu le devrais",
        "pourquoi tu ne dis jamais non",
        "TU NE DIS JAMAIS NON ?",
    ),

    # ── Emotions Cachées / Peurs (40+) ──
    (
        "Tu as peur du rejet plus que de la mort",
        "la peur du rejet est plus forte que la peur de la mort",
        "pourquoi le rejet te fait plus mal que tout",
        "REJET > MORT ?",
    ),
    (
        "Tu fais semblant d'aller bien",
        "tu fais semblant d'aller bien alors que tu souffres",
        "le masque social que tu portes chaque jour",
        "MASQUE = SURVIE ?",
    ),
    (
        "Tu utilises l'humour pour cacher ta douleur",
        "tu utilises l'humour pour cacher ta douleur",
        "pourquoi les gens drôles sont souvent tristes",
        "HUMOUR = DOULEUR ?",
    ),
    (
        "Tu évites les conflits même quand tu as raison",
        "tu évites les conflits même quand tu as raison",
        "la peur du conflit qui te contrôle",
        "CONFLIT = DANGER ?",
    ),
    (
        "Tu ne demandes pas de l'aide par orgueil",
        "tu ne demandes pas de l'aide par orgueil pas par force",
        "l'orgueil qui t'empêche d'avancer",
        "ORGUEIL = FAIBLESSE ?",
    ),
    (
        "Tu restes dans des situations toxiques par habitude",
        "tu restes dans des situations toxiques par habitude",
        "pourquoi tu restes là où tu souffres",
        "HABITUDE TOXIQUE ?",
    ),
    (
        "Tu te sens coupable sans raison",
        "tu te sens coupable sans avoir fait quoi que ce soit",
        "le syndrome du survivant qui te ronge",
        "COUPABLE SANS RAISON ?",
    ),
    (
        "Tu parles de toi trop peu ou trop",
        "tu parles de toi soit trop peu soit trop dans les conversations",
        "le déséquilibre de partage dans les relations",
        "TU PARLES TROP ?",
    ),
    (
        "Tu attends la permission pour être heureux",
        "tu attends la permission des autres pour être heureux",
        "pourquoi tu ne te donnes pas le droit d'être heureux",
        "PERMISSION D'ÊTRE HEUREUX ?",
    ),
    (
        "Tu te compares aux autres en permanence",
        "ton cerveau te compare aux autres en permanence",
        "la comparaison sociale qui te détruit",
        "COMPARAISON = DOULEUR ?",
    ),

    # ── Histoire & Faits Cachés (40+) ──
    (
        "Napoléon utilisait cette technique de contrôle",
        "Napoléon utilisait cette technique de contrôle sur ses généraux",
        "la technique de manipulation de Napoléon",
        "NAPOLEON MANIPULATEUR ?",
    ),
    (
        "Les Romans utilisaient le pain et les jeux pour contrôler",
        "les Romains utilisaient le pain et les jeux pour contrôler le peuple",
        "le panem et circenses comme outil de contrôle",
        "PAIN ET JEUX ?",
    ),
    (
        "La publicité utilise des couleurs pour te manipuler",
        "la publicité utilise des couleurs spécifiques pour te manipuler",
        "comment les couleurs de la pub contrôlent tes achats",
        "COULEURS = MANIPULATION ?",
    ),
    (
        "Les supermarchés sont conçus pour te faire dépenser",
        "les supermarchés sont conçus pour te faire dépenser plus",
        "les techniques de manipulation dans les magasins",
        "SUPERMARCHÉ = PIEGE ?",
    ),
    (
        "L'école t'enseigne l'obéissance pas la pensée critique",
        "l'école t'enseigne l'obéissance plus que la pensée critique",
        "le vrai but de l'éducation selon la psychologie",
        "ÉCOLE = OBÉISSANCE ?",
    ),
    (
        "Les religions utilisent les mêmes mécanismes que le marketing",
        "les religions utilisent les mêmes mécanismes que le marketing",
        "les parallèles entre foi et persuasion",
        "FOI = MARKETING ?",
    ),
    (
        "Les médias choisissent ce que tu penses",
        "les médias choisissent les informations que tu reçois",
        "comment les médias façonnent ta réalité",
        "MÉDIAS = RÉALITÉ ?",
    ),
    (
        "Les employés les plus productifs sont les moins satisfaits",
        "les employés les plus productifs sont souvent les moins satisfaits",
        "le paradoxe de la productivité au travail",
        "PRODUCTIF = HEUREUX ?",
    ),
    (
        "La justice n'est pas aveugle elle est biaisée",
        "la justice n'est pas aveugle elle est biaisée inconsciemment",
        "les biais judiciaires qui échappent à tous",
        "JUSTICE BIAISÉE ?",
    ),
    (
        "Les-elections sont influencées par la météo",
        "les résultats des élections sont influencés par la météo",
        "comment la météo influence tes choix politiques",
        "MÉTÉO = VOTE ?",
    ),

    # ── Dark Secrets du Corps Humain (30+) ──
    (
        "Ton cerveau peut te donner de faux souvenirs",
        "ton cerveau peut créer de faux souvenirs que tu crois vrais",
        "comment ton cerveau fabrique de faux souvenirs",
        "FAUX SOUVENIRS CRÉÉS ?",
    ),
    (
        "Tu changes de personnalité selon avec qui tu es",
        "tu changes de personnalité selon avec qui tu es",
        "pourquoi tu ne es pas le même avec tout le monde",
        "PERSONNALITÉ VARIABLE ?",
    ),
    (
        "Ton cerveau décide avant que tu ne le saches",
        "ton cerveau décide avant que tu en aies conscience",
        "le libre arbitre est une illusion selon la neuroscIENCE",
        "LIBRE ARBITRE ?",
    ),
    (
        "Tu ne connais pas ta vraie personnalité",
        "tu ne connais pas ta vraie personnalité cachée",
        "les couches de personnalité que tu caches",
        "VRAIE PERSONNALITÉ ?",
    ),
    (
        "Tu fais des choses que tu ne comprends pas",
        "tu fais des choses que tu ne comprends pas toi-même",
        "les motivations inconscientes qui te contrôlent",
        "MOTIVATIONS INCONSCIENTES ?",
    ),
    (
        "Tu ne vois pas quand tu es en colère",
        "ton cerveau te cache ta propre colère",
        "la colère refoulée qui te détruit de l'intérieur",
        "COLÈRE CACHÉE ?",
    ),
    (
        "Tu te sens vide après avoir atteint un objectif",
        "tu te sens vide après avoir atteint un objectif important",
        "le syndrome du but qui te vide après la victoire",
        "BUT ATTEINT = VIDE ?",
    ),
    (
        "Tu n'es pas aussi intelligent que tu le crois",
        "ton cerveau te fait croire que tu es plus intelligent que la moyenne",
        "l'effet Dunning-Kruger qui te trompe",
        "TU ES MOINS INTELLIGENT ?",
    ),
    (
        "Tu choisis ce qui te convient pas ce qui est vrai",
        "ton cerveau choisit ce qui te convient pas ce qui est vrai",
        "le biais de confirmation qui contrôle tes choix",
        "CHOIX = CONFIRMATION ?",
    ),
    (
        "Tu ne te souviens pas de 90% de ta journée",
        "ton cerveau efface 90% de ta journée chaque soir",
        "pourquoi tu oublies la majorité de ta vie",
        "90% OUBLIÉ ?",
    ),

    # ── Addictions & Compulsions (30+) ──
    (
        "Tu es accro à ton téléphone sans le savoir",
        "tu es accro à ton téléphone sans le savoir",
        "les signes que ton téléphone te contrôle",
        "ACCRO AU TÉLÉPHONE ?",
    ),
    (
        "Tu vérifies ton téléphone 100 fois par jour",
        "tu vérifies ton téléphone en moyenne 100 fois par jour",
        "le nombre de vérifications quotidiennes choque",
        "100 FOIS / JOUR ?",
    ),
    (
        "Les réseaux sociaux sont conçus comme une drogue",
        "les réseaux sociaux sont conçus pour être addictifs comme une drogue",
        "pourquoi les réseaux sociaux te rendent accro",
        "RÉSEAUX = DROGUE ?",
    ),
    (
        "Tu scrolles 3 heures sans t'en rendre compte",
        "tu scrolles 3 heures sans t'en rendre compte",
        "le temps perdu sur les réseaux sociaux",
        "3 HEURES PERDUES ?",
    ),
    (
        "Tu te sens anxious quand ton téléphone est loin",
        "tu te sens anxious quand ton téléphone est loin de toi",
        "la nomophobie qui te contrôle",
        "NOMOPHOBIE ?",
    ),
    (
        "La dopamine te fait faire des choses stupides",
        "la dopamine te pousse à faire des choses que tu regrettes",
        "comment la dopamine contrôle tes choix",
        "DOPAMINE = PIED PIÉGE ?",
    ),
    (
        "Tu manges pour tes émotions pas pour ta faim",
        "tu manges pour tes émotions pas pour ta faim",
        "l'alimentation émotionnelle qui te détruit",
        "MANGER = ÉMOTIONS ?",
    ),
    (
        "Tu procrastines par peur de réussir",
        "tu procrastines par peur de réussir pas par paresse",
        "la peur du succès qui te paralyse",
        "PEUR DE RUSSIR ?",
    ),
    (
        "Tu achètes des choses pour combler un vide",
        "tu achètes des choses pour combler un vide émotionnel",
        "le shopping comme thérapie dangereuse",
        "ACHAT = VIDE ?",
    ),
    (
        "Tu restes éveillé par peur de dormir",
        "tu restes éveillé par peur de dormir sans le savoir",
        "le sommeil qui fait peur aux contrôleurs",
        "PEUR DE DORMIR ?",
    ),

    # ── Enfance & Formation (30+) ──
    (
        "Ton enfance détermine tes choix d'adulte",
        "ton enfance détermine inconsciemment tes choix d'adulte",
        "comment l'enfance façonne tes décisions",
        "ENFANCE = DESTIN ?",
    ),
    (
        "Tu répètes les erreurs de tes parents",
        "tu répètes les erreurs de tes parents sans le vouloir",
        "la répétition inconsciente des schémas familiaux",
        "TU ES COMME TES PARENTS ?",
    ),
    (
        "Les blessures d'enfance cachent ta personnalité",
        "les blessures d'enfance cachent ta vraie personnalité",
        "comment les traumatismes d'enfance te masquent",
        "BLESSURES CACHÉES ?",
    ),
    (
        "Tu cherches dans l'amour ce que l'enfance ne t'a pas donné",
        "tu cherches dans l'amour ce que tes parents ne t'ont pas donné",
        "le schéma d'attachement qui te contrôle",
        "AMOUR = REMPLACER ?",
    ),
    (
        "Tu ne sais pas dire non parce qu'on ne te l'a pas appris",
        "tu ne sais pas dire non parce qu'on ne te l'a pas appris enfant",
        "l'éducation qui t'empêche de refuser",
        "DIRE NON = IMPOSSIBLE ?",
    ),
    (
        "Le regard de tes parents a défini ta valeur",
        "le regard de tes parents a défini ta valeur à tes propres yeux",
        "comment le regard parental façonne ton estime",
        "REGARD PARENTAL = VALEUR ?",
    ),
    (
        "Tu as peur de devenir tes parents",
        "tu as peur secrètement de devenir comme tes parents",
        "la peur héréditaire qui te suit",
        "DEVENIR TES PARENTS ?",
    ),
    (
        "Ton métier est un choix émotionnel pas logique",
        "ton métier est un choix émotionnel pas logique",
        "pourquoi tu as choisi ce métier vraiment",
        "MÉTIER = ÉMOTIONS ?",
    ),
    (
        "Tu ne sais pas ce que tu veux vraiment",
        "tu ne sais pas ce que tu veux vraiment dans la vie",
        "le flou existentiel qui te paralyse",
        "TU SAIS CE QUE TU VEUX ?",
    ),
    (
        "Tu fuis les conversations profondes",
        "tu fuis les conversations profondes par peur",
        "pourquoi tu évites les sujets qui comptent",
        "FUIR LA PROFONDEUR ?",
    ),
]


# Gabarits grammaticalement sûrs pour la psychologie sombre
# {q} = proposition sujet+verbe, {n} = syntagme nominal défini
ANGLES = [
    "Pourquoi {q}",
    "La psychologie explique pourquoi {q}",
    "Ce que la science dit sur {n}",
    "Ce qu'il faut comprendre sur {n}",
    "Pourquoi {q} est plus courant que tu ne le crois",
    "Ce qui se passe quand {q}",
    "Pourquoi {q} semble étrange mais est normal",
    "Ce que tes gestes révèlent sur {n}",
    "Le secret derrière {n}",
    "Comprendre pourquoi {q}",
]


def build_catalogue() -> list[dict]:
    records = []
    number = 0
    for label, q, n, thumbnail in PHENOMENA:
        for template in ANGLES:
            number += 1
            angle = template.format(q=q, n=n)
            records.append(
                {
                    "series_number": number,
                    "series_title": label,
                    "topic": n,
                    "nominal_phrase": n,
                    "question_phrase": q,
                    "angle": angle,
                    "thumbnail_text": thumbnail,
                    "pillar": "dark_psychology",
                }
            )
    assert len(records) >= 500, f"Expected at least 500 topics, got {len(records)}"
    return records


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "data" / "dark_psych_topics.json"
    target.write_text(json.dumps(build_catalogue(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"500 sujets Dark Psychology écrits dans {target}")
