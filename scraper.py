import os
import requests
from datetime import datetime, timezone
from scoring import calculer_marge

PRIX_REF_M2 = 9800
MELO_API_KEY = os.getenv("MELO_API_KEY", "")
LBC_API_KEY  = os.getenv("LBC_API_KEY", "")
MELO_BASE    = "https://api.notif.immo/documents/properties"


def get_prix_reference_dvf(code_postal="75018"):
    print(f"  [DVF] Prix référence fixe : {PRIX_REF_M2} €/m²")
    return PRIX_REF_M2


def scraper_melo(zone="montmartre"):
    print("  [Melo] Scraping API 900+ sources...")
    annonces = []

    if not MELO_API_KEY:
        print("  [Melo] Clé API manquante")
        return []

    headers = {
        "X-API-KEY":     MELO_API_KEY,
        "Content-Type":  "application/json",
    }

    page = 1
    total_pages = 1

    while page <= total_pages and page <= 10:
        params = {
            "includedZipcodes[]":  "75018",
            "propertyTypes[]":     "0",
            "transactionType":     "0",
            "expired":             "false",
            "order[createdAt]":    "desc",
            "itemsPerPage":        "30",
            "page":                str(
