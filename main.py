"""
main.py — cycle de collecte ParisInvest.

Sourcing par alertes mail : Gmail → parsing → filtre de zone → enrichissement
→ marge et score → Supabase → alerte Telegram.

Deux modes d'exécution :

    python main.py --once      un seul cycle, puis sortie
    python main.py             boucle permanente, un cycle toutes les 10 min

Le mode --once est celui du workflow GitHub Actions. Il est possible parce
que le processus ne porte aucun état : la file d'attente, c'est la boîte
Gmail elle-même. Les alertes restent sous le label `parisinvest` jusqu'à ce
qu'un cycle les traite, donc une interruption décale le traitement sans rien
perdre — et la date de publication reste celle du mail, ce qui préserve le
score de fraîcheur.

L'API Melo a été retirée : elle facturait à l'annonce.
"""
import sys
import time
from datetime import datetime, timezone

import schedule

from config import GMAIL_LABEL, SCORE_ALERTE, SURFACE_MIN, ZONES
import gmail_client
from parsers import parser_lot
from zone_filter import est_dans_zone
from enricher import enrichir_lot
from dedup import id_annonce, empreinte
from scoring import calculer_marge, calculer_score
from ml_scorer import get_preference_vectors, calculer_score_ml
from database import (
    sauvegarder_annonce,
    desactiver_annonces_expirees,
    verifier_urls_mortes,
    recalculer_principaux,
    get_top_annonces,
    get_annonces_deja_alertees,
    enregistrer_alerte,
)
from telegram import envoyer_alerte
from image_proxy import start_proxy_thread

ZONE = "montmartre"

# La vérification des URLs mortes sollicite les portails : une fois par heure
# suffit, alors que le cycle tourne toutes les dix minutes.
CYCLES_ENTRE_PURGES = 6
_compteur_cycles = 0


def _anciennete_en_jours(date_publi):
    if not date_publi:
        return 0
    try:
        if isinstance(date_publi, str):
            publi = datetime.fromisoformat(date_publi.replace("Z", "+00:00"))
        else:
            publi = date_publi
        if publi.tzinfo is None:
            publi = publi.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - publi).days)
    except Exception:
        return 0


def preparer(annonce):
    """Complète une annonce parsée : identifiants, ancienneté, marge, score."""
    annonce["zone"] = ZONE
    annonce["jours_en_ligne"] = _anciennete_en_jours(annonce.get("date_publi"))

    annonce["id"] = id_annonce(
        source=annonce.get("source", ""),
        url=annonce.get("url", ""),
        titre=annonce.get("titre", ""),
        surface=annonce.get("surface", 0),
        prix=annonce.get("prix", 0),
        ref_source=annonce.get("ref_source", ""),
    )
    annonce["empreinte"] = empreinte(
        annonce.get("surface"), pieces=annonce.get("pieces"), zone=ZONE
    )

    marge = calculer_marge(annonce.get("surface"), annonce.get("prix"), zone=ZONE)
    annonce.update(marge)
    return annonce


def collecter():
    """Lit la boîte, retourne les annonces prêtes à être scorées."""
    try:
        alertes = gmail_client.recuperer_alertes()
    except gmail_client.GmailIndisponible as e:
        print(f"  [Gmail] {e}")
        return [], []
    except Exception as e:
        print(f"  [Gmail] Lecture impossible : {e}")
        return [], []

    if not alertes:
        return [], []

    ids_mails = [a["id"] for a in alertes]
    annonces = parser_lot(alertes)
    if not annonces:
        return [], ids_mails

    retenues, hors_zone, trop_petites = [], 0, 0
    for annonce in annonces:
        if float(annonce.get("surface") or 0) < SURFACE_MIN:
            trop_petites += 1
            continue
        if not est_dans_zone(annonce):
            hors_zone += 1
            continue
        retenues.append(preparer(annonce))

    print(f"  [Filtre] {len(retenues)} retenue(s), {hors_zone} hors zone, "
          f"{trop_petites} sous {SURFACE_MIN:.0f} m²")
    return retenues, ids_mails


def alerter(annonces_sauvegardees):
    """Notifie les nouvelles opportunités, une seule fois chacune."""
    top = get_top_annonces(zone=ZONE, limite=15)
    candidates = [a for a in top if (a.get("score") or 0) >= SCORE_ALERTE]
    if not candidates:
        return 0

    deja = get_annonces_deja_alertees([a["id"] for a in candidates])
    envoyees = 0
    for annonce in candidates:
        if annonce["id"] in deja:
            continue
        if envoyer_alerte(annonce):
            enregistrer_alerte(annonce["id"], annonce.get("score"))
            envoyees += 1
    return envoyees


def run():
    global _compteur_cycles
    _compteur_cycles += 1

    print(f"\n{'=' * 56}")
    print(f"Cycle {_compteur_cycles} — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"Zone : {ZONES[ZONE]['libelle']} · "
          f"marché {ZONES[ZONE]['prix_m2_ref']:.0f} €/m² · "
          f"revente {ZONES[ZONE]['prix_revente_m2']:.0f} €/m²")
    print(f"{'=' * 56}")

    desactiver_annonces_expirees()
    if _compteur_cycles % CYCLES_ENTRE_PURGES == 1:
        verifier_urls_mortes()

    annonces, ids_mails = collecter()
    if not annonces:
        print("Aucune annonce exploitable ce cycle.")
        if ids_mails:
            gmail_client.marquer_lot_traite(ids_mails)
        return

    enrichir_lot(annonces)

    print("  [ML] Chargement des préférences...")
    vec_likes, vec_dislikes, nb_likes, nb_dislikes = get_preference_vectors()
    print(f"  [ML] {nb_likes} like(s) / {nb_dislikes} dislike(s)")

    for annonce in annonces:
        score_ml = calculer_score_ml(
            annonce, vec_likes=vec_likes, vec_dislikes=vec_dislikes,
            nb_likes=nb_likes, nb_dislikes=nb_dislikes,
        )
        annonce["score"] = calculer_score(annonce, zone=ZONE, score_ml=score_ml)

    nouvelles = mises_a_jour = 0
    for annonce in annonces:
        resultat = sauvegarder_annonce(annonce)
        if resultat == "nouvelle":
            nouvelles += 1
        elif resultat == "maj":
            mises_a_jour += 1

    recalculer_principaux(zone=ZONE)

    # Les mails ne sont marqués traités qu'une fois la base écrite : si le
    # cycle tombe avant, ils repasseront au cycle suivant.
    gmail_client.marquer_lot_traite(ids_mails)

    envoyees = alerter(annonces)

    print(f"\nCycle terminé — {nouvelles} nouvelle(s), {mises_a_jour} mise(s) à jour, "
          f"{envoyees} alerte(s) envoyée(s)")


def _annoncer_boite():
    try:
        adresse = gmail_client.tester_connexion()
        print(f"  Boîte connectée : {adresse}")
        print(f"  Label surveillé : {GMAIL_LABEL}")
        return True
    except Exception as e:
        print(f"  Gmail inaccessible : {e}")
        return False


def executer_une_fois():
    """Mode GitHub Actions : un cycle, puis sortie."""
    print("ParisInvest — collecte ponctuelle")
    joignable = _annoncer_boite()
    try:
        run()
    except Exception as e:
        print(f"\nCycle interrompu : {e}")
        return 1
    # Une boîte injoignable n'est pas une erreur transitoire : c'est presque
    # toujours un refresh token expiré. On sort en erreur pour que GitHub
    # marque le run en rouge plutôt que de laisser passer des cycles vides.
    return 0 if joignable else 1


def demarrer():
    """Mode serveur : boucle permanente, avec le proxy d'images."""
    print("ParisInvest — sourcing par alertes mail")

    # Les portails bloquent le hotlinking des photos : le front passe par ce
    # proxy pour les afficher. Inutile en mode --once, où rien ne reste en
    # écoute après la sortie.
    start_proxy_thread()

    _annoncer_boite()
    run()
    schedule.every(10).minutes.do(run)
    print("\nWorker actif — un cycle toutes les 10 minutes.")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    if "--once" in sys.argv:
        sys.exit(executer_une_fois())
    demarrer()
