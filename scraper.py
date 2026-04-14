import re
import os
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from scoring import calculer_marge

PRIX_REF_M2 = 9800
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")
LBC_API_KEY = os.getenv("LBC_API_KEY", "")


def get_prix_reference_dvf(code_postal="75018"):
    print(f"  [DVF] Prix référence fixe : {PRIX_REF_M2} €/m²")
    return PRIX_REF_M2


def fetch(url, rss=False):
    """Toutes les requêtes passent par ScraperAPI avec rendu JS."""
    if SCRAPER_API_KEY:
        proxy = (
            f"https://api.scraperapi.com"
            f"?api_key={SCRAPER_API_KEY}"
            f"&url={requests.utils.quote(url, safe='')}"
            f"&render=true"
            f"&wait=3000"
        )
        resp = requests.get(proxy, timeout=60)
    else:
        hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=hdrs, timeout=15)
    return resp


def extraire_prix_surface(texte):
    """Extrait prix et surface depuis un texte quelconque."""
    prix_m = re.search(r"([\d\s\xa0]{3,10})\s*€", texte)
    surf_m = re.search(r"(\d{2,4})\s*m[²2]", texte)
    if not prix_m or not surf_m:
        return None, None
    try:
        prix    = float(re.sub(r"[\s\xa0]", "", prix_m.group(1)))
        surface = float(surf_m.group(1))
        if prix < 50000 or surface < 10:
            return None, None
        return prix, surface
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────
# 1. PAP — parse HTML direct (le RSS nécessite auth)
# ─────────────────────────────────────────────────────────

PAP_URL = "https://www.pap.fr/annonce/ventes-appartements-paris-18e-g439"

def scraper_pap(zone="montmartre"):
    print("  [PAP] Scraping HTML...")
    annonces = []
    try:
        resp = fetch(PAP_URL)
        print(f"  [PAP] Status {resp.status_code} — {len(resp.text)} chars")
        soup = BeautifulSoup(resp.text, "html.parser")

        # Chaque annonce PAP est dans un article ou div avec data-id
        cards = soup.select("a.search-list-item-link, div.search-list-item, article[data-id]")
        print(f"  [PAP] {len(cards)} cards trouvées")

        for card in cards[:40]:
            texte = card.get_text(" ", strip=True)
            lien  = card.get("href", "") or card.select_one("a[href]", {}).get("href", "")
            if lien and not lien.startswith("http"):
                lien = "https://www.pap.fr" + lien

            prix, surface = extraire_prix_surface(texte)
            if not prix or not surface:
                continue

            titre_el = card.select_one("h2, h3, .item-title, .title")
            titre = titre_el.get_text(strip=True) if titre_el else texte[:80]
            dpe_m = re.search(r"DPE\s*:?\s*([A-G])", texte, re.IGNORECASE)
            marge_nette, marge_pct = calculer_marge(surface, prix)

            annonces.append({
                "titre":          titre[:120],
                "adresse":        "Paris 18e",
                "surface":        surface,
                "prix":           prix,
                "prix_m2":        round(prix / surface),
                "dpe":            dpe_m.group(1).upper() if dpe_m else "",
                "source":         "PAP",
                "url":            lien,
                "date_publi":     datetime.now(timezone.utc).isoformat(),
                "jours_en_ligne": 0,
                "nb_baisses":     0,
                "zone":           zone,
                "marge_nette":    marge_nette,
                "marge_pct":      marge_pct,
            })

    except Exception as e:
        print(f"  [PAP] Erreur : {e}")
    print(f"  [PAP] {len(annonces)} annonces parsées")
    return annonces


# ─────────────────────────────────────────────────────────
# 2. Bien'ici — parse HTML direct
# ─────────────────────────────────────────────────────────

BIENICI_URL = (
    "https://www.bienici.com/recherche/achat/paris-18eme-arrondissement-75018"
    "?typesBien=appartement&tri=publication-desc"
)

def scraper_bienici(zone="montmartre"):
    print("  [Bien'ici] Scraping HTML...")
    annonces = []
    try:
        resp = fetch(BIENICI_URL)
        print(f"  [Bien'ici] Status {resp.status_code} — {len(resp.text)} chars")
        soup = BeautifulSoup(resp.text, "html.parser")

        cards = soup.select("article.ad-list-item, div[data-test='adCard'], div.item")
        print(f"  [Bien'ici] {len(cards)} cards trouvées")

        for card in cards[:40]:
            texte = card.get_text(" ", strip=True)
            lien_el = card.select_one("a[href]")
            lien = lien_el.get("href", "") if lien_el else ""
            if lien and not lien.startswith("http"):
                lien = "https://www.bienici.com" + lien

            prix, surface = extraire_prix_surface(texte)
            if not prix or not surface:
                continue

            titre_el = card.select_one("h2, h3, .title, .ad-title")
            titre = titre_el.get_text(strip=True) if titre_el else texte[:80]
            dpe_m = re.search(r"DPE\s*:?\s*([A-G])|[Cc]lasse\s+([A-G])", texte)
            dpe = ""
            if dpe_m:
                dpe = (dpe_m.group(1) or dpe_m.group(2) or "").upper()

            marge_nette, marge_pct = calculer_marge(surface, prix)

            annonces.append({
                "titre":          titre[:120],
                "adresse":        "Paris 18e",
                "surface":        surface,
                "prix":           prix,
                "prix_m2":        round(prix / surface),
                "dpe":            dpe,
                "source":         "Bienici",
                "url":            lien,
                "date_publi":     datetime.now(timezone.utc).isoformat(),
                "jours_en_ligne": 0,
                "nb_baisses":     0,
                "zone":           zone,
                "marge_nette":    marge_nette,
                "marge_pct":      marge_pct,
            })

    except Exception as e:
        print(f"  [Bien'ici] Erreur : {e}")
    print(f"  [Bien'ici] {len(annonces)} annonces parsées")
    return annonces


# ─────────────────────────────────────────────────────────
# 3. LeBonCoin — API partenaire (optionnel)
# ─────────────────────────────────────────────────────────

LBC_API = "https://api.leboncoin.fr/api/adssearch/v4/list"

def scraper_leboncoin(lbc_api_key="", zone="montmartre"):
    if not lbc_api_key:
        print("  [LBC] Clé API manquante — source ignorée")
        return []
    print("  [LBC] Scraping API partenaire...")
    annonces = []
    headers = {
        "Authorization": f"Bearer {lbc_api_key}",
        "Content-Type":  "application/json",
        "User-Agent":    "Mozilla/5.0"
    }
    payload = {
        "filters": {
            "category":    {"id": "9"},
            "enums":       {"ad_type": ["offer"], "real_estate_type": ["1"]},
            "location":    {"zipcode": ["75018"]},
            "ranges":      {"price": {"min": 80000, "max": 900000}}
        },
        "limit": 35, "sort_by": "time", "sort_order": "desc"
    }
    try:
        resp = requests.post(LBC_API, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            print(f"  [LBC] Erreur {resp.status_code}")
            return []
        for ad in resp.json().get("ads", []):
            a = _parser_lbc(ad, zone)
            if a:
                annonces.append(a)
        print(f"  [LBC] {len(annonces)} annonces")
    except Exception as e:
        print(f"  [LBC] Erreur : {e}")
    return annonces

def _parser_lbc(ad, zone):
    try:
        attrs   = {a["key"]: a.get("value_label", a.get("value", ""))
                   for a in ad.get("attributes", [])}
        prix    = float(ad.get("price", [0])[0])
        surface = float(attrs.get("square", 0))
        if prix < 50000 or surface < 10:
            return None
        marge_nette, marge_pct = calculer_marge(surface, prix)
        return {
            "titre":          ad.get("subject", "")[:120],
            "adresse":        ad.get("location", {}).get("city", "Paris 18e"),
            "surface":        surface,
            "prix":           prix,
            "prix_m2":        round(prix / surface),
            "dpe":            attrs.get("energy_rate", ""),
            "source":         "LeBonCoin",
            "url":            f"https://www.leboncoin.fr/ad/{ad.get('list_id', '')}",
            "date_publi":     ad.get("first_publication_date", datetime.now(timezone.utc).isoformat()),
            "jours_en_ligne": 0,
            "nb_baisses":     0,
            "zone":           zone,
            "marge_nette":    marge_nette,
            "marge_pct":      marge_pct,
        }
    except Exception as e:
        print(f"  [LBC] Parse erreur : {e}")
        return None


# ─────────────────────────────────────────────────────────
# Fonction principale
# ─────────────────────────────────────────────────────────

def scraper_toutes_sources(zone="montmartre", lbc_api_key=""):
    print(f"\n--- Scraping toutes sources ({zone}) ---")
    toutes = []
    toutes += scraper_pap(zone)
    toutes += scraper_bienici(zone)
    toutes += scraper_leboncoin(lbc_api_key, zone)
    print(f"Total brut : {len(toutes)} annonces (avant déduplication)")
    return toutes
