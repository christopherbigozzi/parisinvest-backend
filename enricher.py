"""
enricher.py — complète une annonce en visitant sa page.

Les alertes mail donnent le minimum : titre, prix, surface, photo, lien.
Le DPE, la description complète et l'étage n'y figurent presque jamais, alors
que ce sont eux qui disent si le bien est à retravailler.

Prudence de rigueur : SeLoger et Leboncoin filtrent agressivement les robots.
On y va lentement, une fois par annonce, et l'échec n'est jamais bloquant —
une annonce non enrichie garde simplement une note neutre sur le potentiel
travaux.
"""
import random
import os
import re
import unicodedata
from datetime import datetime, timezone
import time

import requests
from bs4 import BeautifulSoup

from zone_filter import lieux_reconnus
from config import ENRICH_MAX

DELAI_ENTRE_APPELS = (2.0, 4.5)   # secondes, tiré au hasard dans l'intervalle

# ─── Relais de pages ─────────────────────────────────────────────────────────
# PAP ne répond pas aux runners GitHub : plages d'IP partagées et connues.
# Constaté le 07/09/2026 sur 39 annonces recollectées — zéro description, zéro
# DPE, zéro adresse — alors que Bien'ici passait sans encombre depuis la même
# machine par son endpoint JSON. Le réseau du runner fonctionne ; c'est PAP
# qui refuse cette adresse.
#
# On repasse donc par la fonction serverless /api/page du front, hébergée sur
# Vercel, dont les IP ne sont pas bannies. Le relais n'est sollicité qu'en
# second recours : une requête directe qui aboutit ne coûte rien à personne.
#
# Les deux variables sont facultatives. Sans elles, le comportement est
# exactement celui d'avant — un échec reste un échec, jamais une exception.
PAGE_PROXY_URL = os.getenv("PAGE_PROXY_URL", "").rstrip("/")
PAGE_PROXY_CLE = os.getenv("PAGE_PROXY_CLE", "")
TIMEOUT            = 12

# Domaines qui ne mènent pas à une page d'annonce. Les alertes SeLoger ne
# contiennent que des liens de tracking : ils répondent 403 à tout client qui
# n'est pas un vrai navigateur, User-Agent réaliste ou non — la détection va
# au-delà des en-têtes. Les viser brûle les places du cycle pour rien : sur le
# cycle du 17/08/2026, les dix tentatives ont échoué sur ces liens, et aucune
# annonce Bien'ici, pourtant dotée d'une URL exploitable, n'a eu sa chance.
DOMAINES_SANS_PAGE = ("click.by.seloger.com",)

# ── Bien'ici : passer par sa ressource JSON ──────────────────────────────────
# La page d'annonce Bien'ici est une application JavaScript : servie telle
# quelle, elle ne contient qu'un « Il est nécessaire d'activer Javascript ».
# Le scraping HTML y est donc sans objet — ce n'est pas un blocage, il n'y a
# rien à lire. Son propre front s'alimente à cette ressource, qui rend le DPE,
# l'étage et la description sans exécuter le moindre script.
RE_BIENICI_ID = re.compile(r"bienici\.com/annonce/([\w\-]+)", re.I)

# ─── Pages PAP ───────────────────────────────────────────────────────────────
# Relevé sur https://www.pap.fr/annonces/appartement-paris-18e-75018-r446300186
# le 07/09/2026. La page se lit sans navigateur — pas de rendu JavaScript, pas
# de blocage — et sa structure est stable :
#
#     Réf. : E63/0186 / Publié le 06 septembre 2026
#     …titre, prix, caractéristiques…
#     …texte du vendeur…
#     Marx Dormoy · Porte de la Chapelle · Colette Besson   ← stations
#     Que pensez-vous du prix ?                             ← début du hors-sujet
#
# Deux gisements que le mail d'alerte ne donne pas : la liste des stations,
# seule localisation exploitable d'une annonce PAP, et la date de publication
# réelle, qui vaut mieux que la date de réception du mail.
RE_PAP = re.compile(r"pap\.fr/annonces?/", re.I)

# Fin du contenu utile : au-delà commencent sondage, formulaires et pied de
# page. On coupe avant, pour ne pas prendre un lieu cité hors de l'annonce.
RE_FIN_PAP = re.compile(
    r"(Que pensez[\s\-]?vous|Imprimer la fiche|Plan du site|Mentions l[ée]gales|"
    r"Fil d.ariane|Nos autres annonces)", re.I)

MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10,
        "novembre": 11, "decembre": 12}
# Dernière ligne du bloc de caractéristiques : « 6.731 € le m² ».
RE_PRIX_M2_PAP = re.compile(r"[\d.,\s]{3,12}€\s*(?:le|/)\s*m[²2]", re.I)

RE_PUBLIE_PAP = re.compile(
    r"Publi[ée]\s+le\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})", re.I)
BIENICI_JSON = "https://www.bienici.com/realEstateAd.json?id={}"


def _etage_depuis_json(valeur):
    """0 → « RDC », 4 → « 4e ». Chaîne vide si l'information manque."""
    if valeur is None or valeur == "":
        return ""
    try:
        niveau = int(valeur)
    except (TypeError, ValueError):
        return ""
    return "RDC" if niveau == 0 else f"{niveau}e"


def appliquer_donnees_bienici(annonce, donnees):
    """
    Reporte sur l'annonce les champs utiles du JSON Bien'ici.

    Ne remplace jamais une valeur déjà connue : le mail fait foi sur le prix et
    la surface, qui servent à l'identité et à la marge. On ne complète que ce
    qui manquait.
    """
    if not isinstance(donnees, dict):
        return False

    rempli = False

    dpe = str(donnees.get("energyClassification") or "").strip().upper()[:1]
    if dpe and dpe in "ABCDEFG" and not annonce.get("dpe"):
        annonce["dpe"] = dpe
        rempli = True

    etage = _etage_depuis_json(donnees.get("floor"))
    if etage and not annonce.get("etage"):
        annonce["etage"] = etage
        rempli = True

    description = str(donnees.get("description") or "").strip()
    if description and not annonce.get("description"):
        annonce["description"] = re.sub(r"\s+", " ", description)[:2000]
        rempli = True

    pieces = donnees.get("roomsQuantity")
    if pieces and not annonce.get("pieces"):
        try:
            annonce["pieces"] = int(pieces)
            rempli = True
        except (TypeError, ValueError):
            pass

    return rempli

ENTETES = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# ── DPE ──────────────────────────────────────────────────────────────────────
# On cherche une lettre isolée à proximité immédiate du mot DPE. Le piège
# classique est d'attraper le GES, affiché juste à côté avec le même format.
MOTIFS_DPE = [
    re.compile(r"(?:DPE|diagnostic\s+de\s+performance[^.]{0,30}?)"
               r"[^A-Za-z0-9]{0,20}\b([A-G])\b", re.I),
    re.compile(r"classe\s+(?:énergie|energie|énergétique|energetique)"
               r"[^A-Za-z0-9]{0,15}\b([A-G])\b", re.I),
    re.compile(r"consommation[^.]{0,40}?\b([A-G])\b\s*(?:kWh|classe)", re.I),
]

MOTIF_ETAGE = re.compile(
    r"\b(\d{1,2})\s*(?:er|ème|eme|e)?\s*étage|\bétage\s*:?\s*(\d{1,2})|"
    r"\b(rez-de-chauss[ée]e|rdc)\b",
    re.I,
)

MOTIF_PIECES = re.compile(r"\b(\d{1,2})\s*pi[èe]ces?\b", re.I)


def _pause():
    time.sleep(random.uniform(*DELAI_ENTRE_APPELS))


def _texte_page(html):
    soup = BeautifulSoup(html, "lxml")
    for balise in soup(["script", "style", "noscript", "svg"]):
        balise.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def extraire_dpe(texte):
    for motif in MOTIFS_DPE:
        m = motif.search(texte)
        if m:
            lettre = m.group(1).upper()
            if lettre in "ABCDEFG":
                return lettre
    return ""


def extraire_etage(texte):
    m = MOTIF_ETAGE.search(texte)
    if not m:
        return ""
    if m.group(3):
        return "RDC"
    numero = m.group(1) or m.group(2)
    return f"{numero}e" if numero else ""


def extraire_pieces(texte):
    m = MOTIF_PIECES.search(texte)
    return int(m.group(1)) if m else 0


def corps_utile_pap(texte):
    """Le texte de la page privé de tout ce qui suit l'annonce elle-même."""
    m = RE_FIN_PAP.search(texte)
    return texte[:m.start()] if m else texte


def date_publication_pap(texte):
    """« Publié le 06 septembre 2026 » → « 2026-09-06 », ou "" si absent."""
    m = RE_PUBLIE_PAP.search(texte)
    if not m:
        return ""
    mois = MOIS.get(_sans_accent(m.group(2)).lower())
    if not mois:
        return ""
    try:
        return datetime(int(m.group(3)), mois, int(m.group(1)),
                        tzinfo=timezone.utc).isoformat()
    except ValueError:
        return ""


def _sans_accent(texte):
    texte = unicodedata.normalize("NFD", str(texte or ""))
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def extraire_description(texte, longueur=1200):
    """
    Faute de sélecteur fiable et commun aux quatre portails, on prend le texte
    de la page. Le scoring n'y cherche que des mots-clés, la précision du
    découpage importe peu.
    """
    return texte[:longueur]


def enrichir(annonce, session=None):
    """
    Complète l'annonce sur place et la retourne. Ne lève jamais : un échec
    d'enrichissement ne doit pas faire tomber le cycle.
    """
    url = annonce.get("url") or ""
    if not url:
        return annonce

    sess = session or requests.Session()

    bienici = RE_BIENICI_ID.search(url)
    if bienici:
        try:
            _pause()
            rep = sess.get(BIENICI_JSON.format(bienici.group(1)),
                           headers=ENTETES, timeout=TIMEOUT)
            if rep.status_code != 200:
                print(f"  [Enrich] {rep.status_code} sur la fiche JSON "
                      f"{bienici.group(1)}")
                return annonce
            if not appliquer_donnees_bienici(annonce, rep.json()):
                print(f"  [Enrich] Fiche JSON sans donnée utile : "
                      f"{bienici.group(1)}")
        except Exception as e:
            print(f"  [Enrich] Échec sur la fiche JSON {bienici.group(1)} : {e}")
        return annonce

    try:
        html = _recuperer_page(url, sess)
        if not html:
            return annonce

        texte = _texte_page(html)
        if len(texte) < 200:
            print(f"  [Enrich] Page vide ou bloquée : {url[:70]}")
            return annonce

        if not annonce.get("dpe"):
            dpe = extraire_dpe(texte)
            if dpe:
                annonce["dpe"] = dpe

        if not annonce.get("etage"):
            etage = extraire_etage(texte)
            if etage:
                annonce["etage"] = etage

        if not annonce.get("pieces"):
            pieces = extraire_pieces(texte)
            if pieces:
                annonce["pieces"] = pieces

        if not annonce.get("description"):
            annonce["description"] = extraire_description(texte)

        if RE_PAP.search(url):
            _appliquer_page_pap(annonce, texte)

    except Exception as e:
        print(f"  [Enrich] Erreur {url[:60]} : {e}")

    return annonce


def _texte_vendeur_pap(corps):
    """Le corps de page privé de son en-tête de navigation."""
    for ancre in (RE_PRIX_M2_PAP, RE_PUBLIE_PAP):
        m = ancre.search(corps)
        if m:
            return corps[m.end():].strip()
    return corps


def _recuperer_page(url, sess):
    """
    Le HTML de la page, ou "" si elle reste hors d'atteinte.

    Deux tentatives : d'abord en direct, puis par le relais Vercel si le
    portail a refusé. Le relais n'est essayé que sur un refus franc ou une
    erreur réseau — pas sur une page vide, qui relève d'autre chose.
    """
    directe = _tenter(url, sess)
    if directe:
        return directe

    if not (PAGE_PROXY_URL and PAGE_PROXY_CLE):
        return ""

    relais = f"{PAGE_PROXY_URL}/api/page"
    print(f"  [Enrich] Refus direct, passage par le relais : {url[:60]}")
    _pause()
    try:
        rep = sess.get(relais, params={"url": url, "cle": PAGE_PROXY_CLE},
                       timeout=TIMEOUT + 8)
        if rep.status_code == 200:
            return rep.text
        detail = ""
        try:
            detail = rep.json().get("erreur", "")
        except Exception:
            pass
        print(f"  [Enrich] Relais {rep.status_code} {detail} sur {url[:55]}")
    except requests.RequestException as e:
        print(f"  [Enrich] Relais injoignable : {type(e).__name__}")
    return ""


def _tenter(url, sess):
    """Une requête directe. Retourne le HTML, ou "" sans jamais lever."""
    try:
        _pause()
        rep = sess.get(url, headers=ENTETES, timeout=TIMEOUT,
                       allow_redirects=True)
        if rep.status_code == 200:
            return rep.text
        print(f"  [Enrich] {rep.status_code} sur {url[:70]}")
    except requests.RequestException as e:
        print(f"  [Enrich] Échec réseau {url[:60]} : {type(e).__name__}")
    return ""


def _appliquer_page_pap(annonce, texte):
    """
    Verse dans l'annonce ce que seule la page PAP contient.

    Les stations sont écrites dans l'adresse et non dans la description : le
    filtre de zone comme le dashboard lisent ce champ, et « Marx Dormoy,
    Porte de la Chapelle » y est plus parlant qu'un « Paris 18e » muet.
    Ce sont des stations *desservant* le bien, pas son adresse — mais c'est
    tout ce que PAP consent à donner, et c'est déjà décisif.
    """
    corps = corps_utile_pap(texte)

    # La description du vendeur, et elle seule : le haut de page est occupé
    # par la navigation du site, où « à rénover » ne veut rien dire. Le bloc
    # de caractéristiques se termine par « 6.731 € le m² », qui sert d'ancre.
    annonce["description"] = extraire_description(_texte_vendeur_pap(corps), 3000)

    hors, butte = lieux_reconnus(corps)
    lieux = hors or butte
    if lieux:
        libelles = ", ".join(l.title() for l in lieux)
        adresse = str(annonce.get("adresse") or "").strip()
        if adresse and libelles.lower() not in adresse.lower():
            annonce["adresse"] = f"{libelles} · {adresse}"[:150]
        elif not adresse:
            annonce["adresse"] = libelles[:150]

    # La date du mail n'est pas celle de l'annonce : PAP réexpédie ses alertes
    # et le rejeu du 07/09/2026 a fait passer des biens de trois semaines pour
    # des nouveautés. La page, elle, date l'annonce.
    publiee = date_publication_pap(corps)
    if publiee:
        annonce["date_publi"] = publiee
    return annonce


def page_atteignable(annonce):
    """
    Une page d'annonce est-elle joignable derrière cette URL ?

    Faux pour un lien vide et pour les liens de tracking, qui ne rendent la
    page qu'à un vrai navigateur.
    """
    url = (annonce.get("url") or "").strip().lower()
    if not url.startswith("http"):
        return False
    return not any(domaine in url for domaine in DOMAINES_SANS_PAGE)


def enrichir_lot(annonces, maximum=None):
    """
    Enrichit au plus `maximum` annonces par cycle, ENRICH_MAX par défaut.

    Au-delà, le cycle s'allonge au point de dépasser son intervalle, et les
    portails finissent par bloquer l'IP appelante — risque bien plus élevé
    depuis un runner GitHub, dont les plages sont partagées et connues, que
    depuis un serveur dédié.
    """
    maximum = ENRICH_MAX if maximum is None else maximum

    manquantes = [a for a in annonces if not a.get("dpe")]
    candidates = [a for a in manquantes if page_atteignable(a)]
    ignorees = len(manquantes) - len(candidates)

    # Les places sont rares : on les donne aux annonces dont la marge
    # justifierait une visite, pas aux premières venues. Sans ce tri, un
    # portail bavard occupe tout le quota et les autres n'ont jamais leur tour.
    candidates.sort(key=lambda a: float(a.get("marge_pct") or 0), reverse=True)
    a_traiter = candidates[:maximum]

    if ignorees:
        print(f"  [Enrich] {ignorees} annonce(s) sans page atteignable "
              f"(lien de tracking), écartée(s)")
    if not a_traiter:
        return annonces

    print(f"  [Enrich] Enrichissement de {len(a_traiter)} annonce(s)...")
    sess = requests.Session()
    reussies = 0
    for annonce in a_traiter:
        avant = annonce.get("dpe")
        enrichir(annonce, session=sess)
        if annonce.get("dpe") and not avant:
            reussies += 1
    print(f"  [Enrich] DPE récupéré sur {reussies}/{len(a_traiter)}")
    return annonces
