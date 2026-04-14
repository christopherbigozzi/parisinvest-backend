import schedule
import time
from datetime import datetime
from config import ZONES, LBC_API_KEY
from scraper import scraper_toutes_sources
from scoring import calculer_score
from database import sauvegarder_annonce, get_top_annonces, desactiver_annonces_expirees
from telegram import envoyer_alerte

PRIX_REF_M2 = 9800


def run():
    print(f"\n{'='*50}")
    print(f"Cycle demarre : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}")

    # Prix de reference fixe 18e arrondissement
    ZONES["montmartre"]["prix_m2_ref"] = PRIX_REF_M2
    print(f"  [DVF] Prix reference fixe : {PRIX_REF_M2} euro/m2")

    # Verifier et desactiver les annonces expirees (30 par cycle)
    desactiver_annonces_expirees()

    # Scraper toutes les sources
    annonces = scraper_toutes_sources(zone="montmartre", lbc_api_key=LBC_API_KEY)

    if not annonces:
        print("Aucune annonce recuperee ce cycle.")
        return

    # Calculer le score pour chaque annonce
    for annonce in annonces:
        annonce["score"] = calculer_score(annonce, zone="montmartre")

    # Sauvegarder en base
    print(f"\nSauvegarde de {len(annonces)} annonces...")
    sauvegardes = 0
    for annonce in annonces:
        try:
            sauvegarder_annonce(annonce)
            sauvegardes += 1
        except Exception as e:
            print(f"  Erreur sauvegarde : {e}")

    print(f"  {sauvegardes}/{len(annonces)} annonces sauvegardees")

    # Alertes Telegram pour les meilleures opportunites
    print("\nVerification alertes...")
    top     = get_top_annonces(zone="montmartre", limite=10)
    alertes = 0
    for a in top:
        if (a.get("score") or 0) >= 75:
            envoyer_alerte(a)
            alertes += 1

    print(f"\nCycle termine — {sauvegardes} annonces, {alertes} alertes")


run()

schedule.every(1).hours.do(run)
print("\nScraper actif — tourne toutes les heures.")

while True:
    schedule.run_pending()
    time.sleep(60)
