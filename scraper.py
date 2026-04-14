import re
import os
import requests
from datetime import datetime, timezone
from scoring import calculer_marge

PRIX_REF_M2 = 9800
SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")
LBC_API_KEY = os.getenv("LBC_API_KEY", "")


def get_prix_reference_dvf(code_postal="75018"):
    print(f"  [DVF] Prix référence fixe : {PRIX_REF_M2} €/m²")
    return PRIX_REF_M2


def fetch_json(url, payload=None, headers=None):
    """Requête JSON directe, sans proxy (APIs qui acceptent les serveurs)."""
    hdrs = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Content-Type": "application/json",
            "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    try:
        if payload:
            resp = requests.post(url, json=payload, headers=hdrs, timeout=30)
        else:
            resp = requests.get(url, headers=hdrs, timeout=30)
        print(f"    Status {resp.status_code} — {len(resp.text)} chars")
        return resp
    except Exception as e:
        print(f"    Erreur requête : {e}")
        return None


# ─────────────────────────────────────────────────────────
# 1. Bien'ici — API JSON publique
# ─────────────────────────────────────────────────────────

BIENICI_API = "https://www.bienici.com/realEstateAds.json"

def scraper_bienici(zone="montmartre"):
    print("  [Bien'ici] Scraping API JSON...")
    annonces = []
    try:
        params = {
            "filters": '{"size":40,"from":0,"filterType":"buy","propertyType":["flat"],'
                       '"zoneIdsByTypes":{"city":[{"id":"75118","label":"Paris 18ème"}]},'
                       '"sortBy":"publicationDate","sortOrder":"desc","onTheMarket":[true]}',
        }
        resp = requests.get(BIENICI_API, params=params,
                            headers={"User-Agent": "Mozilla/5.0",
                                     "Accept": "application/json"},
                            timeout=30)
        print(f"  [Bien'ici] Status {resp.status_code} — {len(resp.text)} chars")

        if resp.status_code != 200:
            return []

        data = resp.json()
        ads  = data.get("realEstateAds", [])
        print(f"  [Bien'ici] {len(ads)} annonces reçues")

        for ad in ads:
            a = _parser_bienici(ad, zone)
            if a:
                annonces.append(a)

    except Exception as e:
        print(f"  [Bien'ici] Erreur : {e}")

    print(f"  [Bien'ici] {len(annonces)} annonces parsées")
    return annonces

def _parser_bienici(ad, zone):
    try:
        prix    = float(ad.get("price", 0))
        surface = float(ad.get("surfaceArea", 0))
        if prix < 50000 or surface < 10:
            return None

        dpe = ad.get("energyClassification", "") or ""
        marge_nette, marge_pct = calculer_marge(surface, prix)

        # Calcul jours en ligne
        date_str = ad.get("publicationDate", "")
        jours = 0
        if date_str:
            try:
                pub = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                jours = (datetime.now(timezone.utc) - pub).days
            except Exception:
                pass

        return {
            "titre":          ad.get("title", f"Appartement {surface}m²")[:120],
            "adresse":        ad.get("address", {}).get("street", "Paris 18e") or "Paris 18e",
            "surface":        surface,
            "prix":           prix,
            "prix_m2":        round(prix / surface),
            "dpe":            dpe.upper()[:1],
            "source":         "Bienici",
            "url":            f"https://www.bienici.com/annonce/{ad.get('id', '')}",
            "date_publi":     date_str or datetime.now(timezone.utc).isoformat(),
            "jours_en_ligne": jours,
            "nb_baisses":     len(ad.get("priceHistory", [])),
            "zone":           zone,
            "marge_nette":    marge_nette,
            "marge_pct":      marge_pct,
        }
    except Exception as e:
        print(f"  [Bien'ici] Parse erreur : {e}")
        return None


# ─────────────────────────────────────────────────────────
# 2. ImmoData API — agrège SeLoger, LBC, PAP, etc.
#    API publique, pas de clé requise
# ─────────────────────────────────────────────────────────

IMMODATA_API = "https://api.immodata.net/v1/ads"

def scraper_immodata(zone="montmartre"):
    print("  [ImmoData] Scraping API...")
    annonces = []
    try:
        params = {
            "transaction": "sale",
            "type":        "apartment",
            "zipCode":     "75018",
            "limit":       40,
            "sort":        "date_desc",
        }
        resp = requests.get(IMMODATA_API, params=params,
                            headers={"User-Agent": "Mozilla/5.0",
                                     "Accept": "application/json"},
                            timeout=20)
        print(f"  [ImmoData] Status {resp.status_code} — {len(resp.text)} chars")

        if resp.status_code != 200:
            return []

        ads = resp.json().get("ads", resp.json().get("results", []))
        print(f"  [ImmoData] {len(ads)} annonces reçues")

        for ad in ads:
            a = _parser_immodata(ad, zone)
            if a:
                annonces.append(a)

    except Exception as e:
        print(f"  [ImmoData] Erreur : {e}")

    print(f"  [ImmoData] {len(annonces)} annonces parsées")
    return annonces

def _parser_immodata(ad, zone):
    try:
        prix    = float(ad.get("price", 0))
        surface = float(ad.get("surface", ad.get("area", 0)))
        if prix < 50000 or surface < 10:
            return None

        dpe = ad.get("dpe", ad.get("energy_class", "")) or ""
        marge_nette, marge_pct = calculer_marge(surface, prix)

        return {
            "titre":          ad.get("title", f"Appartement {surface}m²")[:120],
            "adresse":        ad.get("address", "Paris 18e"),
            "surface":        surface,
            "prix":           prix,
            "prix_m2":        round(prix / surface),
            "dpe":            dpe.upper()[:1],
            "source":         ad.get("source", "ImmoData"),
            "url":            ad.get("url", ad.get("link", "")),
            "date_publi":     ad.get("published_at", datetime.now(timezone.utc).isoformat()),
            "jours_en_ligne": ad.get("days_online", 0),
            "nb_baisses":     ad.get("price_drops", 0),
            "zone":           zone,
            "marge_nette":    marge_nette,
            "marge_pct":      marge_pct,
        }
    except Exception as e:
        print(f"  [ImmoData] Parse erreur : {e}")
        return None


# ─────────────────────────────────────────────────────────
# 3. LeBonCoin — API partenaire (optionnel)
# ─────────────────────────────────────────────────────────

LBC_API_URL = "https://api.leboncoin.fr/api/adssearch/v4/list"

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
        resp = requests.post(LBC_API_URL, headers=headers, json=payload, timeout=15)
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
    toutes += scraper_bienici(zone)
    toutes += scraper_immodata(zone)
    toutes += scraper_leboncoin(lbc_api_key, zone)
    print(f"Total brut : {len(toutes)} annonces (avant déduplication)")
    return toutes
