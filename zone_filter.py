"""
Filtre géographique Montmartre — double approche :
1. GPS ray-casting si coordonnées disponibles
2. Matching du nom de rue dans une liste statique des rues de la zone
3. Fallback : code postal 75018
"""
import re

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

# ─── Rues de la zone Montmartre ───────────────────────────────────────────────
# Source : mairie 18e + WikiGenWeb + périmètre du polygone géojson.io
RUES_ZONE = {
    # Axes principaux
    "abbesses", "lepic", "caulaincourt", "damremont", "lamarck",
    "marcadet", "clignancourt", "clichy", "rochechouart", "ordener",
    "ramey", "custine", "hermel", "championnet", "doudeauville",
    "poteau", "ruisseau", "simart", "muller", "duhesme", "francoeur",
    "berthe", "ravignan", "tholeze", "trois freres", "trois-freres",
    "veronese", "veron", "durantin", "joseph de maistre",
    # Montmartre butte
    "sacre coeur", "sacré-coeur", "tertre", "cortot", "girardon",
    "saules", "bonne", "mont cenis", "chevalier de la barre",
    "lamarck", "poulbot", "norvins", "abreuvoir", "junot",
    "lepic", "steinkerque", "tardieu", "gabrielle", "garreau",
    # Autour
    "fontaine du but", "achille martinet", "flocon", "ronsard",
    "charles nodier", "houdon", "constance", "puget", "chappe",
    "berlioz", "paul albert", "joseph de maistre", "forest",
    "coysevox", "leibniz", "neuf", "ornano", "belliard",
    "championnet", "trezel", "poissonniers", "myrrha", "cave",
    "christiani", "chartres", "goutte d or", "goutte-d-or",
    "richomme", "caille", "stephenson", "marx dormoy",
    # Places et squares
    "place du tertre", "place clichy", "place jules joffrin",
    "place charles dullin", "place dalida", "place pigalle",
    "blanche", "anvers", "barbès", "barbes",
    # Passages et impasses
    "passage ramey", "passage ruelle", "passage des cloys",
    "villa leandre", "cite veron", "cite nollez",
}

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
    """Vérifie si une rue mentionnée dans le texte est dans la zone."""
    rue = extraire_rue(texte)
    if not rue:
        return None  # pas de rue trouvée → inconnu
    rue_norm = rue.lower().strip()
    # Cherche si un mot-clé de la zone est dans le nom de rue extrait
    for mot in RUES_ZONE:
        if mot in rue_norm or rue_norm in mot:
            return True
    return False


# ─── Fonction principale de filtrage ─────────────────────────────────────────
def est_dans_zone(annonce):
    """
    Triple vérification :
    1. GPS ray-casting (le plus fiable)
    2. Nom de rue dans la liste statique
    3. Code postal 75018 (fallback)
    """
    # 1. GPS
    lat = annonce.get("_lat")
    lon = annonce.get("_lon")
    if lat and lon:
        try:
            in_zone = point_in_polygon(float(lat), float(lon))
            if not in_zone:
                return False
            return True
        except Exception:
            pass

    # 2. Vérification par nom de rue dans titre + adresse
    titre   = str(annonce.get("titre") or "")
    adresse = str(annonce.get("adresse") or "")
    texte_complet = titre + " " + adresse

    rue_ok = rue_dans_zone(texte_complet)
    if rue_ok is True:
        return True
    if rue_ok is False:
        # Rue trouvée mais pas dans la zone
        return False

    # 3. Fallback code postal
    if "75018" in adresse or "18e" in adresse.lower() or "18ème" in adresse.lower():
        return True

    # Aucune info fiable → on accepte par bénéfice du doute
    return True
