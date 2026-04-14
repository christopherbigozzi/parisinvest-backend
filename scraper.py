import os
import requests
from datetime import datetime, timezone
from scoring import calculer_marge

PRIX_REF_M2  = 9800
MELO_API_KEY = os.getenv("MELO_API_KEY", "")
LBC_API_KEY  = os.getenv("LBC_API_KEY", "")
MELO_BASE    = "https://api.notif.immo/documents/properties"

# Polygone zone Montmartre (lon, lat) — sens horaire
# Nord-ouest : Caulaincourt/Marcadet
# Nord-est   : Clignancourt/Marcadet
# Sud-est    : Clignancourt/Rochechouart (point ajouté)
# Sud        : Clichy centre
# Sud-ouest  : Caulaincourt/Clichy
MONTMARTRE_GEOSHAPE = [
    ("2.3285", "48.8910"),
    ("2.3482", "48.8910"),
    ("2.3497", "48.8824"),
    ("2.3380", "48.8834"),
    ("2.3285", "48.8834"),
    ("2.3285", "48.8910"),
]


def get_prix_reference_dvf(code_postal="75018"):
    print(f"  [DVF] Prix reference fixe : {PRIX_REF_M2} euro/m2")
    return PRIX_REF_M2


def build_geoshape_params(shape, page, items_per_page=30):
    params = {}
    for i, (lon, lat) in enumerate(shape):
        params[f"geoShapes[0][{i}][0]"] = lon
        params[f"geoShapes[0][{i}][1]"] = lat
    params["propertyTypes[]"]   = "0"
    params["transactionType"]   = "0"
    params["expired"]           = "false"
    params["order[createdAt]"]  = "desc"
    params["itemsPerPage"]      = str(items_per_page)
    params["page"]              = str(page)
    params["withCoherentPrice"] = "true"
    return params


def scraper_melo(zone="montmartre"):
    print("  [Melo] Scraping API 900+ sources (zone Montmartre)...")
    annonces = []

    if not MELO_API_KEY:
        print("  [Melo] Cle API manquante")
        return []

    headers = {
        "X-API-KEY": MELO_API_KEY,
        "Content-Type": "application/json",
    }

    page = 1
    total_pages = 1

    while page <= total_pages and page <= 80:
        params = build_geoshape_params(MONTMARTRE_GEOSHAPE, page)

        try:
            resp = requests.get(MELO_BASE, params=params, headers=headers, timeout=30)
            print(f"  [Melo] Page {page} - Status {resp.status_code}")

            if resp.status_code != 200:
                print(f"  [Melo] Erreur : {resp.text[:200]}")
                break

            data  = resp.json()
            items = data.get("hydra:member", [])
            total = data.get("hydra:totalItems", 0)
            total_pages = max(1, (total + 29) // 30)

            print(f"  [Melo] {len(items)} biens page {page}/{total_pages} (total: {total})")

            for prop in items:
                a = _parser_melo(prop, zone)
                if a:
                    annonces.append(a)

            page += 1

        except Exception as e:
            print(f"  [Melo] Erreur page {page} : {e}")
            break

    print(f"  [Melo] {len(annonces)} annonces parsees au total")
    return annonces


def _parser_melo(prop, zone):
    try:
        prix    = float(prop.get("price") or 0)
        surface = float(prop.get("surface") or 0)
        if prix < 50000 or surface < 10:
            return None

        dpe     = ""
        adverts = prop.get("adverts", []) or []
        if adverts:
            energy = adverts[0].get("energy") or {}
            dpe    = str(energy.get("category") or "")

        nb_baisses = 0
        for advert in adverts:
            for event in (advert.get("events") or []):
                if event.get("fieldName") == "price":
                    variation = event.get("percentVariation") or 0
                    if variation < 0:
                        nb_baisses += 1

        source = "Melo"
        url    = ""
        if adverts:
            pub    = adverts[0].get("publisher") or {}
            source = pub.get("name") or "Melo"
            url    = adverts[0].get("url") or ""

        jours   = 0
        created = prop.get("createdAt") or ""
        if created:
            try:
                pub_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                jours  = (datetime.now(timezone.utc) - pub_dt).days
            except Exception:
                pass

        city_obj = prop.get("city") or {}
        adresse  = city_obj.get("name") or "Paris 18e"

        marge_nette, marge_pct = calculer_marge(surface, prix)

        titre = prop.get("title") or f"Appartement {surface}m2"

        return {
            "titre":          titre[:120],
            "adresse":        adresse,
            "surface":        surface,
            "prix":           prix,
            "prix_m2":        round(prix / surface),
            "dpe":            dpe.upper()[:1],
            "source":         source,
            "url":            url,
            "date_publi":     created or datetime.now(timezone.utc).isoformat(),
            "jours_en_ligne": jours,
            "nb_baisses":     nb_baisses,
            "zone":           zone,
            "marge_nette":    marge_nette,
            "marge_pct":      marge_pct,
        }
    except Exception as e:
        print(f"  [Melo] Parse erreur : {e}")
        return None


def scraper_toutes_sources(zone="montmartre", lbc_api_key=""):
    print(f"\n--- Scraping toutes sources ({zone}) ---")
    toutes = []
    toutes += scraper_melo(zone)
    print(f"Total brut : {len(toutes)} annonces (avant deduplication)")
    return toutes
