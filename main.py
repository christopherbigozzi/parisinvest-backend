import time
import schedule
from datetime import datetime
from scraper import scraper_toutes_sources
from database import sauvegarder_annonce, get_top_annonces
from telegram import envoyer_alerte

def run():
    """Lance un cycle complet : scraping → scoring → sauvegarde → alertes."""
    print(f"\n{'='*50}")
    print(f"Cycle démarré : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}")

    # 1. Scraper toutes les sources
    annonces = scraper_toutes_sources(zone="montmartre")

    if not annonces:
        print("Aucune annonce récupérée ce cycle.")
        return

    # 2. Sauvegarder chaque annonce (avec déduplication auto)
    print(f"\nSauvegarde de {len(annonces)} annonces...")
    nouvelles = 0
    for annonce in annonces:
        try:
            sauvegarder_annonce(annonce)
            nouvelles += 1
        except Exception as e:
            print(f"  Erreur sauvegarde : {e}")

    # 3. Envoyer alertes Telegram pour les meilleures
    print("\nVérification des alertes...")
    top = get_top_annonces(zone="montmartre", limite=10)
    alertes_envoyees = 0
    for annonce in top:
        if annonce["score"] >= 75:
            envoyer_alerte(annonce)
            alertes_envoyees += 1

    print(f"\nCycle terminé — {nouvelles} annonces traitées, {alertes_envoyees} alertes envoyées")

# Lancer immédiatement au démarrage
run()

# Puis toutes les heures
schedule.every(1).hours.do(run)

print("\nScraper actif — tourne toutes les heures. Ctrl+C pour arrêter.")
while True:
    schedule.run_pending()
    time.sleep(60)
