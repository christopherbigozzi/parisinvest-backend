import re
import os
import requests
import feedparser
from datetime import datetime, timezone
from scoring import calculer_score, calculer_marge

# Prix de référence fixe 18e (source DVF 2024)
PRIX_REF_M2 = 9800

# ScraperAPI — contourne les blocages 403
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")

def scraper_url(url):
    """Passe toutes les requêtes via ScraperAPI pour éviter les 403."""
    if SCRAPER_API_KEY:
        proxy_url = (
            f"https://api.scraperapi.com"
            f"?api_key={SCRAPER_API_KEY}"
            f"&url={requests.utils.quote(url, safe='')}"
        )
        resp = requests.get(proxy_url, timeout=30)
    else:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=15)
    return resp


def get_prix_reference_dvf(code_postal="75018"):
    print(f"  [DVF] Prix référence fixe : {PRIX_REF_M2} €/m²")
    return PRIX_REF_M2


# ─────────────────────────────────────────────────────────
# 1. PAP — Flux RSS
# ─────────────────────────────────────────────────────────

PAP_RSS = "https://www.pap.fr/annonce/ventes-appartements-paris-18e-g439?_feed=rss"

def scraper_pap(zone="montmartre"):
    print("  [PAP] Scraping RSS...")
    annonces = []
    try:
        resp = scraper_url(PAP_RSS)
        print(f"  [PAP] Status {resp.status_code} — {len(resp.text)} chars")
        feed = feedparser.parse(resp.text)
        print(f"  [PAP] {len(feed.entries)} entrées dans le feed")
        for entry in feed.entries[:40]:
            a = _parser_pap(entry, zone)
            if a:
                annonces.append(a)
    except Exception as e:
        print(f"  [PAP] Erreur : {e}")
    print(f"  [PAP] {len(annonces)} annonces parsées")
    return annonces

def _parser_pap(entry, zone):
    try:
        titre = entry.get("title", "")
        desc  = entry.get("summary", "")
        texte = titre + " " + desc

        prix_m = re.search(r"([\d\s]{4,10})\s*€", texte)
        surf_m = re.search(r"(\d{2,4})\s*m[²2]", texte)
        if not prix_m or not surf_m:
            return None

        prix    = float(prix_m.group(1).replace(" ", "").replace("\xa0", ""))
        surface = float(surf_m.group(1))
        if prix < 50000 or surface < 10:
            return None

        dpe_m = re.search(r"DPE\s*:?\s*([A-G])", texte, re.IGNORECASE)
        marge_nette, marge_pct = calculer_marge(surface, prix)

        return {
            "titre":          titre[:120],
            "adresse":        "Paris 18e",
            "surface":        surface,
            "prix":           prix,
            "prix_m2":        round(prix / surface),
            "dpe":            dpe_m.group(1).upper() if dpe_m else "",
            "source":         "PAP",
            "url":            entry.get("link", ""),
            "date_publi":     entry.get("published", datetime.now(timezone.utc).isoformat()),
            "jours_en_ligne": 0,
            "nb_baisses":     0,
            "zone":           zone,
            "marge_nette":    marge_nette,
            "marge_pct":      marge_pct,
        }
    except Exception as e:
        print(f"  [PAP] Parse erreur : {e}")
        return None


# ─────────────────────────────────────────────────────────
# 2. SeLoger — Flux RSS
# ─────────────────────────────────────────────────────────

SELOGER_RSS = (
    "https://www.seloger.com/list.htm"
    "?idtypebien=1&idtt=2&cp=75018&tri=initial_date_desc&output=rss"
)

def scraper_seloger(zone="montmartre"):
    print("  [SeLoger] Scraping RSS...")
    annonces = []
    try:
        resp = scraper_url(SELOGER_RSS)
        print(f"  [SeLoger] Status {resp.status_code} — {len(resp.text)} chars")
        feed = feedparser.parse(resp.text)
        print(f"  [SeLoger] {len(feed.entries)} entrées dans le feed")
        for entry in feed.entries[:40]:
            a = _parser_seloger(entry, zone)
            if a:
                annonces.append(a)
    except Exception as e:
        print(f"  [SeLoger] Erreur : {e}")
    print(f"  [SeLoger] {len(annonces)} annonces parsées")
    return annonces

def _parser_seloger(entry, zone):
    try:
        titre = entry.get("title", "")
        desc  = entry.get("summary", "")
        texte = titre + " " + desc

        prix_m = re.search(r"([\d\s\xa0]{4,10})\s*€", texte)
        surf_m = re.search(r"(\d{2,4})\s*m[²2]?", texte)
        if not prix_m or not surf_m:
            return None

        prix    = float(re.sub(r"[\s\xa0]", "", prix_m.group(1)))
        surface = float(surf_m.group(1))
        if prix < 50000 or surface < 10:
            return None

        dpe_m = re.search(r"classe[^\w]*([A-G])", texte, re.IGNORECASE)
        marge_nette, marge_pct = calculer_marge(surface, prix)

        return {
            "titre":          titre[:120],
            "adresse":        "Paris 18e",
            "surface":        surface,
            "prix":           prix,
            "prix_m2":        round(prix / surface),
            "dpe":            dpe_m.group(1).upper() if dpe_m else "",
            "source":         "SeLoger",
            "url":            entry.get("link", ""),
            "date_publi":     entry.get("published", datetime.now(timezone.utc).isoformat()),
            "jours_en_ligne": 0,
            "nb_baisses":     0,
            "zone":           zone,
            "marge_nette":    marge_nette,
            "marge_pct":      marge_pct,
        }
    except Exception as e:
        print(f"  [SeLoger] Parse erreur : {e}")
        return None


# ─────────────────────────────────────────────────────────
# 3. LeBonCoin — API partenaire (optionnel)
# ─────────────────────────────────────────────────────────

LBC_API = "https://api.leboncoin.fr/api/adssearch/v4/list"

def scraper_leboncoin(lbc_api_key="", zone="montmartre"):
    if not lbc_api_key:
        print("  [LBC] Clé API manquante — source ignorée pour l'instant")
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
        "limit":      35,
        "sort_by":    "time",
        "sort_order": "desc"
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
            "date_publi":     ad.get("first_publication_date",
                                     datetime.now(timezone.utc).isoformat()),
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
    toutes += scraper_seloger(zone)
    toutes += scraper_leboncoin(lbc_api_key, zone)
    print(f"Total brut : {len(toutes)} annonces (avant déduplication)")
    return toutes
