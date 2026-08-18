"""
Filtre géographique Montmartre — double approche :
1. GPS ray-casting si coordonnées disponibles
2. Matching du nom de rue dans une liste statique des rues de la zone
3. Fallback : code postal 75018
"""
import re
import unicodedata


def _aplatir(texte):
    """
    « Barbès-Rochechouart » → « barbes rochechouart ».

    Accents retirés, ponctuation et tirets réduits à des espaces : un même lieu
    s'écrit de dix façons dans les annonces, la comparaison doit être aveugle
    à ces variantes.
    """
    texte = unicodedata.normalize("NFD", str(texte or "").lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return " " + re.sub(r"[^a-z0-9]+", " ", texte).strip() + " "

# ─── Polygone Montmartre (lat, lon) ───────────────────────────────────────────
MONTMARTRE_POLYGON = [
    [48.89006616583566,  2.3399816318652427],
    [48.88968475443497,  2.334657271277621],
    [48.88672871742938,  2.3332070563311333],
    [48.88456266233064,  2.3321090364430574],
    [48.88265536633,     2.338386395424777],
    [48.88243738501271,  2.3396915888756666],
    [48.883908740467774, 2.346901228893387],
    [48.88683769885438,  2.347357010733475],
    [48.88930334012477,  2.346196838776649],
    [48.89039308757785,  2.3420948022153993],
    [48.88995719144694,  2.3385935689883013],
    [48.8897119982031,   2.334553684495063],
]

# ─── Périmètre retenu : la Butte stricte ─────────────────────────────────────
# L'ancienne liste mélangeait la Butte et tout le reste du 18e, de la Goutte
# d'Or à la Porte de Clignancourt. Comme le filtre acceptait par ailleurs tout
# ce qui portait 75018, le classement se remplissait de biens bon marché de
# quartiers qu'on ne vise pas : ils affichent de meilleures marges et
# occupaient les premières places.
#
# Ces deux listes sont le cœur du réglage — à ajuster selon ta connaissance du
# terrain, elles priment sur tout le reste.

RUES_BUTTE = {
    # Versants et sommet
    "abbesses", "lepic", "ravignan", "berthe", "tholeze", "tholozé",
    "trois freres", "trois-freres", "durantin", "veron", "gabrielle",
    "garreau", "norvins", "saules", "cortot", "girardon", "junot",
    "poulbot", "abreuvoir", "mont cenis", "chevalier de la barre",
    "muller", "tertre", "sacre coeur", "sacré-coeur", "paul albert",
    "andre barsacq", "drevet", "dalida", "villa leandre", "cite nollez",
    "burq", "aristide bruant", "yvonne le tac", "la vieuville", "orsel",
    "germain pilon", "coustou", "piemontesi", "andre antoine", "feutrier",
    "nicolet", "seveste", "livingstone", "antoinette", "veron",
    # Flancs nord et ouest
    "caulaincourt", "lamarck", "francoeur", "saint vincent",
    # Pied sud, côté Anvers et Sacré-Cœur
    "steinkerque", "tardieu", "ronsard", "chappe", "houdon",
    "constance", "puget", "charles nodier", "anvers",
    "place du tertre", "place dalida", "place charles dullin",
}

# Rues, squares et quartiers explicitement hors périmètre. Une seule de ces
# mentions, où que ce soit dans le titre, l'adresse ou la description, suffit à
# écarter l'annonce — c'est le tout premier contrôle, avant même le quartier
# annoncé par le portail.
#
# Les termes sont comparés après passage par _aplatir : écrire « barbes »
# couvre « Barbès », « BARBÈS » et « Barbès-Rochechouart ».
#
# Prudence sur les mots courants : « cave », « blanche », « forest », « poteau »
# ou « ruisseau » se rencontrent dans n'importe quelle description de bien. Ils
# figurent donc ici précédés de leur type de voie, jamais seuls.
LIEUX_HORS_ZONE = {
    # ── La Chapelle et Marx Dormoy ───────────────────────────────────────────
    "la chapelle", "porte de la chapelle", "marx dormoy", "pajol", "riquet",
    "philippe de girard", "torcy", "cugnot", "evangile", "aubervilliers",
    "departement", "tanger", "curial", "cesaria evora", "max dormoy",
    # ── Barbès et la Goutte d'Or ─────────────────────────────────────────────
    "barbes", "goutte d or", "chateau rouge", "poulet", "polonceau",
    "myrha", "myrrha", "panama", "laghouat", "saint bruno", "affre",
    "islettes", "charbonniere", "leon", "doudeauville", "richomme",
    "stephenson", "caplat", "suez", "myrha", "boris vian", "gardes",
    "rue de chartres", "rue cave", "rue de la charbonniere",
    "square leon", "square saint bernard",
    # ── Porte de Clignancourt, Simplon, Amiraux ──────────────────────────────
    "porte de clignancourt", "porte des poissonniers", "porte de saint ouen",
    "clignancourt", "simplon", "amiraux", "belliard", "championnet",
    "vauvenargues", "jean dollfus", "binet", "camille flammarion",
    "boulevard ney", "rue du poteau", "rue du ruisseau", "moskowa",
    "square des amiraux",
    # ── Jules Joffrin, Marcadet, Clignancourt bas ────────────────────────────
    "jules joffrin", "marcadet", "poissonniers", "ramey", "custine",
    "hermel", "ordener", "simart", "duhesme", "cloys", "christiani",
    "trezel", "letort", "eugene sue", "montcalm", "emile duployé",
    "square jules joffrin",
    # ── Grandes-Carrières, Guy Môquet, La Fourche ────────────────────────────
    "damremont", "joseph de maistre", "coysevox", "leibniz", "guy moquet",
    "la fourche", "rue forest", "brochant", "la jonquiere", "epinettes",
    "square des epinettes",
    # ── Bordure sud : Pigalle, Blanche, Place de Clichy, Anvers-Rochechouart ─
    "pigalle", "place blanche", "rue blanche", "place de clichy",
    "place clichy", "rochechouart", "boulevard de clichy",
    # ── Arrondissements limitrophes, repères cités dans les descriptions ─────
    # Les agences vendent un quartier voisin en nommant son métro ou son
    # église. « NOTRE DAME DE LORETTE » ouvrait une annonce du 9e classée
    # 75018 par l'alerte, relevée le 18/08/2026.
    "notre dame de lorette", "faubourg montmartre", "saint georges",
    "la trinite", "cadet", "grands boulevards", "le peletier",
    "saint lazare", "batignolles", "cardinet", "rome", "villiers",
    "stalingrad", "jaures", "colonel fabien", "belleville", "crimee",
    "porte de la villette", "corentin cariou", "laumiere",
}

# Conservée sous son ancien nom : d'autres modules l'importent peut-être.
RUES_ZONE = RUES_BUTTE

# Quartiers tels que SeLoger les nomme dans ses alertes.
QUARTIERS_ZONE = {"montmartre"}
QUARTIERS_HORS_ZONE = {
    "clignancourt-jules joffrin", "goutte d'or-château rouge",
    "goutte d'or", "la chapelle", "grandes-carrières", "grandes carrieres",
    "porte de clignancourt", "amiraux-simplon",
}

# « Paris 19e », « 75019 », « 19ème arrondissement » dans un titre : le bien
# n'est pas chez nous, même si l'alerte le range en 75018.
RE_AUTRE_ARRONDISSEMENT = re.compile(
    # Codes postaux parisiens : 75001 à 75020. L'ancien motif s'écrivait
    # 75(0\d|1[0-9]|20), qui ne peut pas reconnaître cinq chiffres — la règle
    # « autre code postal » ne s'est donc jamais déclenchée.
    r"\b750(0[1-9]|1[0-9]|20)\b"
    r"|\b(\d{1,2})\s*[eè]{1,2}(?:me)?\s*(?:arr|arrondissement)"
    # « Paris 19 », « PARIS 18 » : le numéro suit directement la ville. Le
    # caractère qui suit est parfois abîmé à l'encodage — « Paris 19? » vu le
    # 17/08/2026 — d'où l'absence d'exigence sur le suffixe. On écarte en
    # revanche « Paris 3 pièces » et « Paris 60 m² », où le nombre n'est pas
    # un arrondissement.
    r"|\bparis\s*(\d{1,2})(?!\s*(?:pi[èe]ce|p\b|chambre|m[²2]|\d))",
    re.I,
)

# ─── Algorithme ray-casting ───────────────────────────────────────────────────
def point_in_polygon(lat, lon, polygon=MONTMARTRE_POLYGON):
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lon_i = polygon[i][0], polygon[i][1]
        lat_j, lon_j = polygon[j][0], polygon[j][1]
        if ((lon_i > lon) != (lon_j > lon)) and \
           (lat < (lat_j - lat_i) * (lon - lon_i) / (lon_j - lon_i) + lat_i):
            inside = not inside
        j = i
    return inside


# ─── Extraction de rue depuis un texte ────────────────────────────────────────
def extraire_rue(texte):
    """Extrait le nom de rue depuis un titre ou une description."""
    if not texte:
        return ""
    texte = texte.lower()
    # Patterns courants dans les annonces immobilières
    patterns = [
        r"rue\s+([\w\s\-\']+?)(?:\s*[-,\|]|\s+\d|\s+paris|\s*$)",
        r"boulevard\s+([\w\s\-\']+?)(?:\s*[-,\|]|\s+\d|\s+paris|\s*$)",
        r"avenue\s+([\w\s\-\']+?)(?:\s*[-,\|]|\s+\d|\s+paris|\s*$)",
        r"impasse\s+([\w\s\-\']+?)(?:\s*[-,\|]|\s+\d|\s+paris|\s*$)",
        r"passage\s+([\w\s\-\']+?)(?:\s*[-,\|]|\s+\d|\s+paris|\s*$)",
        r"place\s+([\w\s\-\']+?)(?:\s*[-,\|]|\s+\d|\s+paris|\s*$)",
        r"villa\s+([\w\s\-\']+?)(?:\s*[-,\|]|\s+\d|\s+paris|\s*$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, texte)
        if m:
            return m.group(1).strip()
    return ""


def rue_dans_zone(texte):
    """
    True si la rue citée est une rue de la Butte, None sinon.

    Volontairement, une rue inconnue ne vaut plus rejet. La Butte compte des
    dizaines de voies et la liste ne sera jamais complète : « rue Burq », bien
    sur la Butte, était absente et faisait écarter un bien légitime. Le rejet
    est désormais l'affaire de la seule liste noire, qui est explicite ; la
    liste blanche ne sert qu'à confirmer.
    """
    rue = extraire_rue(texte)
    if not rue:
        return None
    rue_norm = _aplatir(rue)
    for mot in RUES_BUTTE:
        cle = _aplatir(mot).strip()
        if f" {cle} " in rue_norm or rue_norm.strip() in cle:
            return True
    return None


def _normaliser(texte):
    return _aplatir(texte)


def autre_arrondissement(texte):
    """
    Le texte annonce-t-il un arrondissement autre que le 18e ?

    Cas réel du 17/08/2026 : « Paris 19? Élégant 2/3 pièces avec fort
    potentiel » arrivait en tête du classement, l'alerte SeLoger l'ayant
    rangée en 75018.
    """
    for m in RE_AUTRE_ARRONDISSEMENT.finditer(texte or ""):
        for capture in m.groups():
            if capture and capture.lstrip("0") != "18":
                return True
    return False


def lieu_hors_zone(texte):
    """Un lieu explicitement hors Butte apparaît-il dans le texte ?"""
    plat = _aplatir(texte)
    return any(f" {_aplatir(lieu).strip()} " in plat for lieu in LIEUX_HORS_ZONE)


def motif_exclusion(texte):
    """Renvoie le terme qui a fait rejeter l'annonce, pour pouvoir l'expliquer."""
    plat = _aplatir(texte)
    for lieu in sorted(LIEUX_HORS_ZONE, key=len, reverse=True):
        if f" {_aplatir(lieu).strip()} " in plat:
            return lieu
    return ""


def localisation_verifiee(annonce):
    """
    La localisation repose-t-elle sur une information explicite ?

    Vraie si des coordonnées GPS existent, si le portail nomme un quartier, ou
    si une rue de la Butte est citée quelque part.

    Fausse quand on ne dispose que de « 75018 ». C'est le cas des alertes
    SeLoger au format « exclusivités d'agence », qui ne contiennent aucun bloc
    de localisation : ni quartier, ni rue, ni métro. Ces annonces sont
    invérifiables depuis le mail, et comme les quartiers bon marché du 18e y
    sont surreprésentés, elles affichent les meilleures marges apparentes et
    monopolisaient le haut du classement.
    """
    if annonce.get("_lat") and annonce.get("_lon"):
        return True

    if quartier_connu(str(annonce.get("adresse") or "")) is not None:
        return True

    texte = " ".join(str(annonce.get(c) or "")
                     for c in ("titre", "adresse", "description"))
    plat = _aplatir(texte)
    # Une rue de la Butte, ou le nom du quartier lui-même : les agences
    # écrivent souvent « MONTMARTRE » en tête de description.
    reperes = set(RUES_BUTTE) | set(QUARTIERS_ZONE)
    return any(f" {_aplatir(repere).strip()} " in plat for repere in reperes)


def quartier_connu(adresse):
    """
    Verdict d'après le quartier nommé par le portail : True, False, ou None
    si aucun quartier connu n'apparaît. SeLoger le donne, Bien'ici non.
    """
    plat = _normaliser(adresse)
    for quartier in QUARTIERS_HORS_ZONE:
        if quartier in plat:
            return False
    for quartier in QUARTIERS_ZONE:
        if quartier in plat:
            return True
    return None


# ─── Fonction principale de filtrage ─────────────────────────────────────────
def est_dans_zone(annonce):
    """
    Vérifications, dans l'ordre où elles s'appliquent :
    1. Lieu explicitement exclu, n'importe où dans le texte — rejet sans appel
    2. Autre arrondissement annoncé — rejet
    3. GPS
    4. Quartier nommé par le portail
    5. Nom de rue
    6. Code postal, en dernier recours
    """
    titre   = str(annonce.get("titre") or "")
    adresse = str(annonce.get("adresse") or "")
    description = str(annonce.get("description") or "")
    texte_complet = " ".join((titre, adresse, description))

    # 1. Le crible passe avant tout le reste, y compris avant le quartier et le
    #    GPS. Une annonce étiquetée « Montmartre » par SeLoger mais dont le
    #    titre mentionne Barbès n'était plus contrôlée : le quartier tranchait
    #    en premier et la laissait passer.
    if lieu_hors_zone(texte_complet):
        return False

    # 2. Un autre arrondissement annoncé quelque part, même si l'alerte range
    #    le bien en 75018.
    if autre_arrondissement(texte_complet):
        return False

    # 3. GPS
    lat = annonce.get("_lat")
    lon = annonce.get("_lon")
    if lat and lon:
        try:
            return point_in_polygon(float(lat), float(lon))
        except Exception:
            pass

    # 4. Le quartier nommé par le portail : la localisation la plus fiable
    #    dont on dispose ensuite.
    verdict = quartier_connu(adresse)
    if verdict is not None:
        return verdict

    # 5. Une rue de la Butte citée : confirmation. Une rue inconnue ne dit
    #    rien et n'entraîne plus de rejet.
    if rue_dans_zone(texte_complet) is True:
        return True

    # 6. Un autre code postal parisien dans l'adresse est un rejet net.
    autre_cp = re.search(r"\b750(0[1-9]|1[0-9]|20)\b", adresse)
    if autre_cp and autre_cp.group(0) != "75018":
        return False

    # 7. Reste le 75018 sans autre indice. On accepte, faute de mieux : les
    #    alertes mail ne donnent pas de GPS et beaucoup de titres restent
    #    muets sur la localisation. C'est le point d'entrée du bruit qui
    #    subsiste — les étapes 2 à 5 sont là pour le réduire, pas pour
    #    l'éliminer. Une annonce arrivée jusqu'ici mérite un coup d'œil avant
    #    déplacement.
    return True
