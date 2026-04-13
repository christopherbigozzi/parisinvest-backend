import requests
import feedparser
from datetime import datetime
from config import JINKA_API_KEY, ZONES
from scoring import calculer_score, calculer_marge

# ─────────────────────────────────────────
# JINKA API  (agrège SeLoger, LBC, PAP, Bienici, etc.)
# ─────────────────────────────────────────

def scraper_jinka(zone="montmartre"):
    """Récupère les annonces via l'API Jinka."""
    print("Scraping Jinka...")
    annonces = []

    headers = {
        "Authorization": f"Bearer {JINKA_API_KEY}",
        "Content-Type": "application/json"
    }

    # Paramètres de recherche pour le 18e arrondissement
    params = {
        "transaction": "buy",
        "property_type": "flat",
        "zip_codes": ["75018"],
        "min_surface": 20,
        "max_price": 800000,
        "page": 1,
        "per_page": 50
    }

    try:
        resp = requests.get(
            "https://api.jinka.fr/apiv2/alert/search",
            headers=headers,
            json=params,
            timeout=15
        )
        if resp.status_code != 200:
            print(f"  Jinka erreur {resp.status_code}")
            return []

        data = resp.json()
        for item in data.get("ads", []):
            annonce = parser_annonce_jinka(item, zone)
            if annonce:
                annonces.append(annonce)

        print(f"  {len(annonces)} annonces Jinka récupérées")

    except Exception as e:
        print(f"  Jinka exception : {e}")

    return annonces


def parser_annonce_jinka(item, zone):
    """Convertit une annonce Jinka en format standard."""
    try:
        prix = float(item.get("price", 0))
        surface = float(item.get("surface", 0))
        if prix == 0 or surface == 0:
            return None

        prix_m2 = round(prix / surface)
        marge_nette, marge_pct = calculer_marge(surface, prix)

        annonce = {
            "titre": item.get("title", ""),
            "adresse": item.get("city", "") + " " + item.get("zip_code", ""),
            "surface": surface,
            "prix": prix,
            "prix_m2": prix_m2,
            "dpe": item.get("energy_rate", ""),
            "source": item.get("source_label", "Jinka"),
            "url": item.get("url", ""),
            "date_publi": item.get("published_at", datetime.now().isoformat()),
            "jours_en_ligne": item.get("days_online", 0),
            "nb_baisses": item.get("price_drops", 0),
            "zone": zone,
            "marge_nette": marge_nette,
            "marge_pct": marge_pct,
        }
        annonce["score"] = calculer_score(annonce, zone)
        return annonce
    except Exception as e:
        print(f"  Erreur parsing Jinka item : {e}")
        return None


# ─────────────────────────────────────────
# PAP — Flux RSS (gratuit, légal, temps réel)
# ─────────────────────────────────────────

PAP_RSS_URL = (
    "https://www.pap.fr/annonce/ventes-appartements-paris-18e-g439-"
    "?_feed=atom"
)

def scraper_pap(zone="montmartre"):
    """Récupère les annonces PAP via le flux RSS."""
    print("Scraping PAP RSS...")
    annonces = []

    try:
        feed = feedparser.parse(PAP_RSS_URL)
        for entry in feed.entries[:30]:
            annonce = parser_annonce_pap(entry, zone)
            if annonce:
                annonces.append(annonce)

        print(f"  {len(annonces)} annonces PAP récupérées")

    except Exception as e:
        print(f"  PAP exception : {e}")

    return annonces


def parser_annonce_pap(entry, zone):
    """Parse une entrée RSS PAP."""
    try:
        titre = entry.get("title", "")
        desc = entry.get("summary", "")

        # Extraire le prix depuis le titre/description
        import re
        prix_match = re.search(r"([\d\s]+)\s*€", titre + " " + desc)
        surface_match = re.search(r"([\d]+)\s*m²", titre + " " + desc)

        if not prix_match or not surface_match:
            return None

        prix = float(prix_match.group(1).replace(" ", ""))
        surface = float(surface_match.group(1))
        if prix < 50000 or surface < 10:
            return None

        prix_m2 = round(prix / surface)
        marge_nette, marge_pct = calculer_marge(surface, prix)

        annonce = {
            "titre": titre,
            "adresse": "Paris 18e",
            "surface": surface,
            "prix": prix,
            "prix_m2": prix_m2,
            "dpe": "",
            "source": "PAP",
            "url": entry.get("link", ""),
            "date_publi": entry.get("published", datetime.now().isoformat()),
            "jours_en_ligne": 0,
            "nb_baisses": 0,
            "zone": zone,
            "marge_nette": marge_nette,
            "marge_pct": marge_pct,
        }
        annonce["score"] = calculer_score(annonce, zone)
        return annonce

    except Exception as e:
        print(f"  Erreur parsing PAP entry : {e}")
        return None


# ─────────────────────────────────────────
# Fonction principale — toutes les sources
# ─────────────────────────────────────────

def scraper_toutes_sources(zone="montmartre"):
    """Lance tous les scrapers et retourne toutes les annonces."""
    toutes = []
    toutes += scraper_jinka(zone)
    toutes += scraper_pap(zone)
    print(f"Total brut : {len(toutes)} annonces (avant déduplication)")
    return toutes
