import schedule
import time
from datetime import datetime
from config import ZONES, LBC_API_KEY
from scraper import scraper_toutes_sources, get_prix_reference_dvf
from database import sauvegarder_annonce, get_top_annonces
from telegram import envoyer_alerte

def run():
    print(f"\n{'='*50}")
    print(f"Cycle démarré : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}")

    # 1. Mettre à jour le prix de référence DVF (open data État)
    prix_dvf = get_prix_reference_dvf("75018")
    if prix_dvf:
        ZONES["montmartre"]["prix_m2_ref"] = prix_dvf

    # 2. Scraper toutes les sources (PAP + SeLoger + LBC si clé dispo)
    annonces = scraper_toutes_sources(zone="montmartre", lbc_api_key=LBC_API_KEY)

    if not annonces:
        print("Aucune annonce récupérée ce cycle.")
        return

    # 3. Sauvegarder avec déduplication automatique
    print(f"\nSauvegarde de {len(annonces)} annonces...")
    for annonce in annonces:
        try:
            sauvegarder_annonce(annonce)
        except Exception as e:
            print(f"  Erreur sauvegarde : {e}")

    # 4. Alertes Telegram pour les meilleures opportunités
    print("\nVérification alertes...")
    top = get_top_annonces(zone="montmartre", limite=10)
    alertes = 0
    for a in top:
        if a["score"] >= 75:
            envoyer_alerte(a)
            alertes += 1

    print(f"\nCycle terminé — {len(annonces)} annonces traitées, {alertes} alertes envoyées")

# Lancer immédiatement au démarrage
# DEBUG temporaire — affiche la structure HTML de PAP
from scraper import fetch
resp = fetch("https://www.pap.fr/annonce/ventes-appartements-paris-18e-g439")
from bs4 import BeautifulSoup
soup = BeautifulSoup(resp.text, "html.parser")
# Affiche les 20 premiers tags avec classe pour trouver les bons sélecteurs
tags = soup.find_all(class_=True)[:30]
for t in tags:
    classes = " ".join(t.get("class", []))
    texte = t.get_text(strip=True)[:60]
    print(f"  <{t.name} class='{classes}'> {texte}")


# Puis toutes les heures
schedule.every(1).hours.do(run)
print("\nScraper actif — tourne toutes les heures.")

while True:
    schedule.run_pending()
    time.sleep(60)
