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
import re
import time

import requests
from bs4 import BeautifulSoup

from config import ENRICH_MAX

DELAI_ENTRE_APPELS = (2.0, 4.5)   # secondes, tiré au hasard dans l'intervalle
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
        _pause()
        rep = sess.get(url, headers=ENTETES, timeout=TIMEOUT, allow_redirects=True)
        if rep.status_code != 200:
            print(f"  [Enrich] {rep.status_code} sur {url[:70]}")
            return annonce

        texte = _texte_page(rep.text)
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

    except requests.RequestException as e:
        print(f"  [Enrich] Échec réseau {url[:60]} : {type(e).__name__}")
    except Exception as e:
        print(f"  [Enrich] Erreur {url[:60]} : {e}")

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
