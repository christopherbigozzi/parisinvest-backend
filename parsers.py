"""
parsers.py — extraction des annonces depuis le corps des alertes mail.

Principe commun aux quatre portails : le corps du mail est une succession de
blocs, un par annonce, et chaque bloc contient plusieurs liens vers la même
page d'annonce. On repère donc toutes les occurrences d'un lien d'annonce,
on découpe le texte aux changements d'identifiant, et on lit les champs à
l'intérieur de chaque bloc.

Ce découpage résiste aux refontes graphiques : tant que le mail contient un
lien par annonce et le prix en toutes lettres à côté, il continue de marcher.
Un parseur fondé sur les classes CSS casserait à la première refonte.

Choix du corps à lire : un mail d'alerte arrive en multipart/alternative, avec
une version texte et une version HTML. La version texte porte les URL en clair.
La version HTML est plus longue, mais ses liens passent souvent par le traceur
du portail, qui encode l'URL de destination dans un paramètre — le motif de
lien ne la reconnaît alors plus, et le mail ressort vide. On essaie donc les
corps l'un après l'autre et on garde le premier qui produit des blocs, au lieu
de choisir le plus long.

État de calibrage :
  bienici    calibré sur des mails réels du 12/08/2026 et du 17/08/2026
  seloger    à confirmer sur un mail réel
  jinka      à confirmer sur un mail réel
  leboncoin  à confirmer sur un mail réel
"""
import re
from datetime import datetime, timezone
from urllib.parse import unquote

from bs4 import BeautifulSoup

# ─── Expressions communes ────────────────────────────────────────────────────
# Les portails écrivent les prix avec des espaces insécables et fines.
RE_PRIX = re.compile(r"(\d[\d    .]{2,12})\s*€")
RE_SURFACE = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*m²", re.I)
RE_PIECES = re.compile(r"(\d{1,2})\s*pi[èe]ces?", re.I)
# La localisation occupe généralement sa propre ligne : « 75018 Paris 18e ».
# On l'ancre sur la ligne pour ne pas confondre avec les blocs de contact des
# agences, où le code postal est collé au numéro de téléphone
# (« Paris 18ème 7501801 42 52 40 00 »).
RE_CP_VILLE = re.compile(r"^\s*(\d{5})\s+([A-Za-zÀ-ÿ][^\n\[]{0,40}?)\s*$", re.M)
RE_CP_VILLE_LARGE = re.compile(r"\b(\d{5})\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ0-9' \-]{0,30})")
RE_REFERENCE = re.compile(r"R[ÉE]F[ÉE]RENCE\s*:?\s*([A-Za-z0-9/\-_]+)", re.I)
RE_TITRE = re.compile(
    r"^((?:Appartement|Maison|Studio|Loft|Duplex|Immeuble|Local|Terrain|Villa|Ch[âa]teau)"
    r"[^\n]{0,120})$",
    re.I | re.M,
)

TYPES_BIEN = re.compile(
    r"\b(appartement|studio|duplex|loft|maison|villa|immeuble|local|terrain)\b", re.I
)


def _nombre(brut):
    """« 1 495 000 » → 1495000.0, en tolérant tous les espaces exotiques."""
    if brut is None:
        return 0.0
    propre = re.sub(r"[^\d,.]", "", str(brut).replace(",", "."))
    if propre.count(".") > 1:  # séparateur de milliers pris pour une décimale
        propre = propre.replace(".", "")
    try:
        return float(propre)
    except ValueError:
        return 0.0


def texte_depuis_html(html):
    """Convertit le HTML du mail en texte en gardant les liens sur leur ligne."""
    soup = BeautifulSoup(html, "lxml")
    for balise in soup(["style", "script", "head"]):
        balise.decompose()
    for a in soup.find_all("a", href=True):
        a.append(f" [{a['href']}] ")
    for img in soup.find_all("img", src=True):
        img.replace_with(f" [{img['src']}] ")
    texte = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", texte)


# ─── Configuration par portail ───────────────────────────────────────────────
# lien_annonce : capture l'identifiant de l'annonce dans l'URL
# lien_photo   : capture l'identifiant dans l'URL de la photo, pour rattacher
#                l'image au bon bloc
PORTAILS = {
    "bienici": {
        "lien_annonce": re.compile(r"https?://(?:www\.)?bienici\.com/annonce/([\w\-]+)"),
        "lien_photo":   re.compile(r"https?://file\.bienici\.com/photo/([\w\-]+?)_[^\s\]]+"),
        "base_url":     "https://www.bienici.com/annonce/{}",
    },
    "seloger": {
        "lien_annonce": re.compile(
            r"https?://(?:www\.)?seloger\.com/(?:annonces/[^\s\]]*?|[^\s\]]*?)"
            r"(\d{6,})\.htm"
        ),
        "lien_photo":   re.compile(r"https?://v\.seloger\.com/s/[^\s\]]+"),
        "base_url":     "https://www.seloger.com/annonces/{}.htm",
    },
    "jinka": {
        "lien_annonce": re.compile(r"https?://(?:www\.)?jinka\.fr/[^\s\]]*?ad[=/]([\w\-]+)"),
        "lien_photo":   re.compile(r"https?://[^\s\]]*jinka[^\s\]]*\.(?:jpg|jpeg|png|webp)"),
        "base_url":     "https://www.jinka.fr/alert_result_view?ad={}",
    },
    "leboncoin": {
        "lien_annonce": re.compile(r"https?://(?:www\.)?leboncoin\.fr/[^\s\]]*?/(\d{8,})"),
        "lien_photo":   re.compile(r"https?://img\.leboncoin\.fr/[^\s\]]+"),
        "base_url":     "https://www.leboncoin.fr/ad/ventes_immobilieres/{}",
    },
    "pap": {
        "lien_annonce": re.compile(r"https?://(?:www\.)?pap\.fr/annonces/[^\s\]]*?(r\d{6,})"),
        "lien_photo":   re.compile(r"https?://[^\s\]]*pap\.fr[^\s\]]+\.(?:jpg|jpeg|png)"),
        "base_url":     "https://www.pap.fr/annonces/{}",
    },
}


def _decouper_en_blocs(texte, motif_lien):
    """
    Retourne [(identifiant, bloc_texte)] en découpant à chaque changement
    d'identifiant d'annonce.
    """
    occurrences = [(m.start(), m.group(1)) for m in motif_lien.finditer(texte)]
    if not occurrences:
        return []

    # Regroupe les occurrences consécutives partageant le même identifiant.
    segments = []
    for position, ident in occurrences:
        if segments and segments[-1][1] == ident:
            continue
        segments.append((position, ident))

    blocs = []
    for i, (debut, ident) in enumerate(segments):
        fin = segments[i + 1][0] if i + 1 < len(segments) else len(texte)
        # On remonte un peu en amont : le titre précède parfois le premier lien.
        marge = max(0, debut - 200) if i == 0 else debut
        blocs.append((ident, texte[marge:fin]))
    return blocs


def _extraire_titre(bloc):
    m = RE_TITRE.search(bloc)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip()[:150]
    # Repli : première ligne mentionnant un type de bien
    for ligne in bloc.split("\n"):
        ligne = ligne.strip()
        if 8 < len(ligne) < 150 and TYPES_BIEN.search(ligne) and "http" not in ligne:
            return re.sub(r"\s+", " ", ligne)[:150]
    return ""


def _extraire_prix(bloc):
    """
    Retient le plus grand montant du bloc. Les mails mélangent le prix de vente
    avec des montants secondaires — honoraires, charges, prix au m² — et le
    prix de vente est systématiquement le plus élevé.
    """
    montants = [_nombre(m.group(1)) for m in RE_PRIX.finditer(bloc)]
    montants = [v for v in montants if 30000 <= v <= 20000000]
    return max(montants) if montants else 0.0


def _extraire_photo(bloc, motif_photo):
    if not motif_photo:
        return None
    m = motif_photo.search(bloc)
    if not m:
        return None
    url = m.group(0).rstrip(".,);]")
    return url or None


def parser_bloc(ident, bloc, source, config):
    surface_match = RE_SURFACE.search(bloc)
    surface = _nombre(surface_match.group(1)) if surface_match else 0.0
    prix = _extraire_prix(bloc)

    if surface <= 0 or prix <= 0:
        return None

    pieces_match = RE_PIECES.search(bloc)
    pieces = int(_nombre(pieces_match.group(1))) if pieces_match else 0

    adresse = "Paris 18e"
    cp_match = RE_CP_VILLE.search(bloc) or RE_CP_VILLE_LARGE.search(bloc)
    if cp_match:
        adresse = f"{cp_match.group(1)} {cp_match.group(2).strip()}"[:120]

    ref_match = RE_REFERENCE.search(bloc)

    lien = config["lien_annonce"].search(bloc)
    url = lien.group(0) if lien else config["base_url"].format(ident)

    return {
        "source":     source,
        "ref_source": ref_match.group(1) if ref_match else "",
        "ident":      ident,
        "titre":      _extraire_titre(bloc) or f"Appartement {surface:.0f} m²",
        "adresse":    adresse,
        "surface":    surface,
        "pieces":     pieces,
        "prix":       prix,
        "prix_m2":    round(prix / surface) if surface else 0,
        "url":        url,
        "photo":      _extraire_photo(bloc, config.get("lien_photo")),
        "dpe":        "",
        "description": "",
    }


def _candidats_corps(alerte):
    """
    Corps possibles du mail, du plus fiable au moins fiable.

    Ordre : la version texte d'abord, puis la version HTML convertie, puis les
    deux repassées par unquote. Ce dernier passage déplie les liens de tracking
    du genre .../click?u=https%3A%2F%2Fwww.bienici.com%2Fannonce%2F..., dont
    l'URL encodée échappe au motif de lien.

    On ne choisit plus « le corps le plus long » : le HTML l'est presque
    toujours, et c'est justement celui dont les liens sont tracés.
    """
    html = alerte.get("html") or ""
    corps = [alerte.get("texte") or ""]
    if html:
        corps.append(texte_depuis_html(html))

    candidats = []
    for brut in corps:
        if not brut:
            continue
        candidats.append(brut)
        deplie = unquote(brut)
        if deplie != brut:
            candidats.append(deplie)
    return candidats


def parser_alerte(alerte):
    """
    Transforme un mail d'alerte en liste d'annonces.

    `alerte` est un dictionnaire produit par gmail_client.recuperer_alertes.
    """
    source = alerte.get("source")
    config = PORTAILS.get(source)
    if not config:
        print(f"  [Parse] Portail non géré : {source}")
        return []

    blocs = []
    for candidat in _candidats_corps(alerte):
        blocs = _decouper_en_blocs(candidat, config["lien_annonce"])
        if blocs:
            break

    if not blocs:
        print(f"  [Parse] Aucun lien d'annonce trouvé ({source}) : "
              f"{alerte.get('sujet','')[:60]}")
        return []

    recu = alerte.get("date") or datetime.now(timezone.utc)
    annonces, vus = [], set()

    for ident, bloc in blocs:
        if ident in vus:
            continue
        vus.add(ident)
        annonce = parser_bloc(ident, bloc, source, config)
        if not annonce:
            continue
        annonce["date_publi"] = recu.isoformat() if hasattr(recu, "isoformat") else str(recu)
        annonce["gmail_id"] = alerte.get("id", "")
        annonces.append(annonce)

    print(f"  [Parse] {source} : {len(annonces)} annonce(s) extraite(s) "
          f"de « {alerte.get('sujet','')[:45]} »")
    return annonces


def parser_lot(alertes):
    toutes = []
    for alerte in alertes:
        try:
            toutes += parser_alerte(alerte)
        except Exception as e:
            print(f"  [Parse] Erreur sur « {alerte.get('sujet','')[:40]} » : {e}")
    return toutes
