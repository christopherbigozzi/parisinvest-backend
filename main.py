import schedule
import time
from datetime import datetime
from config import ZONES, LBC_API_KEY
from scraper import scraper_toutes_sources
from scoring import calculer_score
from ml_scorer import get_preference_vectors, calculer_score_ml
from database import sauvegarder_annonce, get_top_annonces, desactiver_annonces_expirees
from telegram import envoyer_alerte
from image_proxy import start_proxy_thread

PRIX_REF_M2 = 9800


def run():
    print(f"\n{'='*50}")
    print(f"Cycle demarre : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}")

    ZONES["montmartre"]["prix_m2_ref"] = PRIX_REF_M2
    print(f"  [DVF] Prix reference fixe : {PRIX_REF_M2} euro/m2")

    desactiver_annonces_expirees()

    print("  [ML] Chargement preferences utilisateur...")
    vec_likes, vec_dislikes, nb_likes, nb_dislikes = get_preference_vectors()
    print(f"  [ML] {nb_likes} likes / {nb_dislikes} dislikes")

    annonces = scraper_toutes_sources(zone="montmartre", lbc_api_key=LBC_API_KEY)

    if not annonces:
        print("Aucune annonce recuperee ce cycle.")
        return

    for annonce in annonces:
        score_ml = calculer_score_ml(
            annonce,
            vec_likes=vec_likes,
            vec_dislikes=vec_dislikes,
            nb_likes=nb_likes,
            nb_dislikes=nb_dislikes,
        )
        annonce["score"] = calculer_score(annonce, zone="montmartre", score_ml=score_ml)

    print(f"\nSauvegarde de {len(annonces)} annonces...")
    sauvegardes = 0
    for annonce in annonces:
        try:
            sauvegarder_annonce(annonce)
            sauvegardes += 1
        except Exception as e:
            print(f"  Erreur sauvegarde : {e}")

    print(f"  {sauvegardes}/{len(annonces)} annonces sauvegardees")

    print("\nVerification alertes...")
    top     = get_top_annonces(zone="montmartre", limite=10)
    alertes = 0
    for a in top:
        if (a.get("score") or 0) >= 75:
            envoyer_alerte(a)
            alertes += 1

    print(f"\nCycle termine — {sauvegardes} annonces, {alertes} alertes")


# Démarrer le proxy d'images en arrière-plan
start_proxy_thread()

run()

schedule.every(10).minutes.do(run)
print("\nScraper actif — tourne toutes les 10 minutes.")

while True:
    schedule.run_pending()
    time.sleep(60)
