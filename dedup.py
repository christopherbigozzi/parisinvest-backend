"""
dedup.py — identifiants d'annonce et regroupement inter-portails.

Deux notions distinctes, que l'ancienne version confondait :

  id       identifie une PUBLICATION. Le même appartement publié sur SeLoger
           et sur Bien'ici donne deux id différents. Stable dans le temps,
           il sert de clé primaire et permet de suivre les baisses de prix.

  empreinte  identifie un BIEN. Elle regroupe les publications qui décrivent
           très probablement le même appartement, pour n'en afficher qu'une
           ligne au dashboard avec la liste de ses sources.

L'ancien `generer_id` hachait adresse + surface + prix arrondi à 5 000 €.
Comme les alertes mail ne donnent presque jamais la rue, l'adresse valait
« Paris 18e » pour tout le monde : deux 30 m² distincts à 450 000 € se
retrouvaient fusionnés en une seule annonce, et le second écrasait le premier.
"""
import hashlib
import re
from urllib.parse import urlsplit, parse_qsl, urlencode, urlunsplit

# Paramètres d'URL purement analytiques, à retirer avant de hacher.
PARAMS_PARASITES = re.compile(
    r"^(utm_|xtor|xts|cmpid|mtm_|pk_|gclid|fbclid|mc_|_ga|origin|source|"
    r"from|ref|referrer|campaign|tracking|cid|sid|uid|email|token)",
    re.I,
)

MOTS_VIDES = {
    "appartement", "appart", "studio", "duplex", "loft", "vente", "vendre",
    "paris", "montmartre", "18e", "18eme", "75018", "de", "du", "des", "la",
    "le", "les", "un", "une", "et", "en", "a", "à", "au", "aux", "avec",
    "sur", "dans", "pour", "pieces", "pièces", "piece", "pièce", "m2", "m²",
}


def normaliser_url(url):
    """Retire le bruit d'une URL pour qu'elle identifie stablement l'annonce."""
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()

    hote = (parts.netloc or "").lower()
    if hote.startswith("www."):
        hote = hote[4:]

    params = [
        (cle, val) for cle, val in parse_qsl(parts.query, keep_blank_values=False)
        if not PARAMS_PARASITES.match(cle)
    ]
    params.sort()

    chemin = (parts.path or "").rstrip("/").lower()
    return urlunsplit(("https", hote, chemin, urlencode(params), ""))


def _hacher(*morceaux):
    brut = "|".join(str(m).strip().lower() for m in morceaux)
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()[:32]


def id_annonce(source, url="", titre="", surface=0, prix=0, ref_source=""):
    """
    Clé primaire d'une publication.

    Ordre de préférence :
      1. référence interne du portail, quand le mail la donne — la plus stable
      2. URL normalisée
      3. repli sur source + titre + surface + prix, pour les mails sans lien
    """
    if ref_source:
        return _hacher(source, "ref", ref_source)

    url_propre = normaliser_url(url)
    if url_propre:
        return _hacher(source, "url", url_propre)

    return _hacher(source, "brut", titre[:80], round(float(surface or 0)),
                   round(float(prix or 0) / 1000))


def empreinte(surface, prix=0, pieces=0, zone="montmartre"):
    """
    Clé de regroupement, volontairement grossière : surface au m² près,
    nombre de pièces, zone.

    Le prix en est délibérément absent. Une première version l'arrondissait
    par paliers de 5 000 € ; deux portails affichant 685 000 € et 690 000 €
    pour le même appartement tombaient alors dans deux paliers voisins et ne
    se regroupaient jamais. Tout découpage en paliers a ce défaut aux
    frontières. L'empreinte se contente donc de rassembler des candidats
    plausibles, et c'est `meme_bien` qui tranche, avec une tolérance
    relative sur le prix.

    Le paramètre `prix` est conservé pour compatibilité d'appel mais ignoré.
    """
    surface = round(float(surface or 0))
    if surface <= 0:
        return ""
    return _hacher("bien", zone, surface, int(pieces or 0))


def grouper(annonces):
    """
    Regroupe des publications décrivant le même bien.

    Retourne une liste de listes. Le regroupement est transitif au sein d'un
    même seau d'empreinte : si A rejoint B et B rejoint C, les trois forment
    un seul groupe, même si A et C ne se ressemblent pas directement.
    """
    seaux = {}
    for a in annonces:
        cle = a.get("empreinte") or empreinte(
            a.get("surface"), pieces=a.get("pieces"),
            zone=a.get("zone") or "montmartre",
        ) or f"seul-{a.get('id')}"
        seaux.setdefault(cle, []).append(a)

    groupes = []
    for membres in seaux.values():
        clusters = []
        for annonce in membres:
            rejoint = None
            for cluster in clusters:
                if any(meme_bien(annonce, autre) for autre in cluster):
                    rejoint = cluster
                    break
            if rejoint is None:
                clusters.append([annonce])
            else:
                rejoint.append(annonce)
        groupes.extend(clusters)
    return groupes


def _jetons(titre):
    mots = re.findall(r"[a-zà-ÿ0-9]+", (titre or "").lower())
    return {m for m in mots if len(m) > 2 and m not in MOTS_VIDES}


def similarite_titre(titre_a, titre_b):
    """Indice de Jaccard sur les mots signifiants. Entre 0 et 1."""
    a, b = _jetons(titre_a), _jetons(titre_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def meme_bien(annonce_a, annonce_b, tolerance_prix=0.02, tolerance_surface=1.0):
    """
    Deux publications décrivent-elles le même appartement ?

    L'empreinte seule ne suffit pas : sur un marché étroit comme la Butte,
    deux 30 m² à 450 000 € peuvent parfaitement coexister. On exige donc en
    plus une surface et un prix proches, et soit un recoupement de titre,
    soit une adresse identique renseignée au-delà de l'arrondissement.
    """
    try:
        surf_a, surf_b = float(annonce_a.get("surface") or 0), float(annonce_b.get("surface") or 0)
        prix_a, prix_b = float(annonce_a.get("prix") or 0), float(annonce_b.get("prix") or 0)
    except (TypeError, ValueError):
        return False

    if min(surf_a, surf_b) <= 0 or min(prix_a, prix_b) <= 0:
        return False
    if abs(surf_a - surf_b) > tolerance_surface:
        return False
    if abs(prix_a - prix_b) / max(prix_a, prix_b) > tolerance_prix:
        return False

    pieces_a = int(annonce_a.get("pieces") or 0)
    pieces_b = int(annonce_b.get("pieces") or 0)
    if pieces_a and pieces_b and pieces_a != pieces_b:
        return False

    adr_a = (annonce_a.get("adresse") or "").strip().lower()
    adr_b = (annonce_b.get("adresse") or "").strip().lower()
    adresse_precise = (
        adr_a and adr_a == adr_b
        and not re.fullmatch(r"paris\s*(1[0-9]|20)?\s*e?(me)?", adr_a)
    )
    if adresse_precise:
        return True

    return similarite_titre(annonce_a.get("titre"), annonce_b.get("titre")) >= 0.45
