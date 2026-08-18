"""
scoring.py — modèle de marge et score d'opportunité.

Marge AVANT FISCALITÉ. Le régime d'imposition se traite au cas par cas sur
les annonces retenues, il n'entre pas dans le classement.

Répartition du score, sur 100 :
    fraîcheur de l'annonce ....... 20
    marge nette .................. 50
    décote vs prix de marché ..... 25
    potentiel travaux ............  5
    bonus baisses de prix ........ +5, plafonné à 100
    localisation invérifiable .... −20

Note : les deux composantes « décote vs DVF » et « prix/m² vs moyenne » de la
version précédente mesuraient la même chose et pesaient 30 points à elles deux.
Elles sont fusionnées ici en une seule composante de 25 points.

Les 25 points de préférences apprises (ML) sont retirés : sans like ni dislike
enregistré, ils valaient zéro pour toute annonce, ce qui plafonnait le score
réel à 75 — exactement la valeur de SCORE_ALERTE, rendant l'alerte inatteignable.
Leur poids est reporté sur la marge, qui passe de 25 à 50 points.

Conséquence à connaître : marge et décote sont, à surface donnée, deux
fonctions du prix au m². Elles pèsent désormais 75 points à elles deux, donc
le classement suit très largement le prix au m². C'est assumé — mais si le
classement paraît un jour trop monolithique, c'est ici qu'il faut regarder.
"""
import os
import re

from zone_filter import localisation_verifiee
from config import (
    TRAVAUX_PAR_M2,
    FRAIS_NOTAIRE,
    DUREE_PORTAGE_MOIS,
    TAUX_FINANCEMENT,
    CHARGES_PORTAGE_M2,
    FRAIS_AGENCE_REVENTE,
    ZONES,
)

# Mots-clés signalant un bien à retravailler : c'est là que se fait la marge.
MOTS_TRAVAUX = re.compile(
    r"\b(à rénover|a renover|à rafraîchir|a rafraichir|à moderniser|a moderniser|"
    r"travaux|plateau|à restaurer|a restaurer|dans son jus|jus d'époque|"
    r"potentiel|à réhabiliter|a rehabiliter|gros œuvre|gros oeuvre|"
    r"succession|viager libre|au plus offrant)\b",
    re.I,
)

# Mots-clés signalant au contraire un bien déjà valorisé : peu de marge à prendre.
MOTS_REFAIT = re.compile(
    r"\b(refait à neuf|refait a neuf|entièrement rénové|entierement renove|"
    r"rénové avec goût|renove avec gout|prestations haut de gamme|"
    r"standing|neuf|livré|livre neuf)\b",
    re.I,
)


def parametres_zone(zone="montmartre"):
    z = ZONES.get(zone) or ZONES["montmartre"]
    return z["prix_m2_ref"], z["prix_revente_m2"]


def calculer_marge(surface, prix_achat, zone="montmartre", travaux_m2=None,
                   prix_revente_m2=None):
    """
    Détail du calcul, tous postes explicites pour être affichable tel quel
    dans le dashboard.
    """
    surface    = float(surface or 0)
    prix_achat = float(prix_achat or 0)
    if surface <= 0 or prix_achat <= 0:
        return _marge_vide()

    ref_m2, revente_m2_defaut = parametres_zone(zone)
    travaux_m2      = TRAVAUX_PAR_M2 if travaux_m2 is None else float(travaux_m2)
    prix_revente_m2 = revente_m2_defaut if prix_revente_m2 is None else float(prix_revente_m2)

    travaux      = surface * travaux_m2
    notaire      = prix_achat * FRAIS_NOTAIRE
    duree_annees = DUREE_PORTAGE_MOIS / 12.0

    portage_financier = (prix_achat + travaux) * TAUX_FINANCEMENT * duree_annees
    portage_charges   = surface * CHARGES_PORTAGE_M2 * duree_annees
    portage           = portage_financier + portage_charges

    prix_revente  = surface * prix_revente_m2
    frais_revente = prix_revente * FRAIS_AGENCE_REVENTE

    cout_total  = prix_achat + travaux + notaire + portage + frais_revente
    marge_nette = prix_revente - cout_total
    marge_pct   = (marge_nette / cout_total * 100) if cout_total > 0 else 0.0

    return {
        "travaux":       round(travaux),
        "notaire":       round(notaire),
        "portage":       round(portage),
        "frais_revente": round(frais_revente),
        "prix_revente":  round(prix_revente),
        "cout_total":    round(cout_total),
        "marge_nette":   round(marge_nette),
        "marge_pct":     round(marge_pct, 1),
        "prix_m2":       round(prix_achat / surface),
        "prix_m2_ref":   round(ref_m2),
    }


def _marge_vide():
    return {
        "travaux": 0, "notaire": 0, "portage": 0, "frais_revente": 0,
        "prix_revente": 0, "cout_total": 0, "marge_nette": 0, "marge_pct": 0.0,
        "prix_m2": 0, "prix_m2_ref": 0,
    }


def _points_fraicheur(jours):
    for seuil, pts in ((0, 20), (1, 18), (3, 14), (7, 9), (14, 5), (30, 2)):
        if jours <= seuil:
            return pts
    return 0


def _points_marge(marge_pct):
    """50 points : l'ancien barème sur 25, doublé, mêmes paliers."""
    for seuil, pts in ((30, 50), (25, 42), (20, 34), (15, 24), (10, 14), (5, 6)):
        if marge_pct >= seuil:
            return pts
    return 2 if marge_pct > 0 else 0


def _points_decote(prix_m2, prix_ref):
    if not (prix_m2 > 0 and prix_ref > 0):
        return 0
    decote = (prix_ref - prix_m2) / prix_ref
    for seuil, pts in ((0.25, 25), (0.20, 21), (0.15, 17), (0.10, 12), (0.05, 6)):
        if decote >= seuil:
            return pts
    return 2 if decote >= 0 else 0


def _points_travaux(dpe, texte):
    """
    5 points au maximum. Le DPE reste le signal principal quand il est
    disponible ; à défaut, on lit le vocabulaire de l'annonce.
    """
    dpe = str(dpe or "").upper().strip()[:1]
    pts_dpe = {"G": 5, "F": 4, "E": 3, "D": 2, "C": 1}.get(dpe)
    if pts_dpe is not None:
        return pts_dpe
    if dpe in ("A", "B"):
        return 0

    texte = texte or ""
    if MOTS_REFAIT.search(texte):
        return 0
    if MOTS_TRAVAUX.search(texte):
        return 5
    return 2  # information absente : note neutre, ni prime ni pénalité


def _points_baisses(nb):
    return {0: 0, 1: 1, 2: 3}.get(nb, 5)


# Pénalité appliquée quand rien, dans l'annonce, ne permet de situer le bien
# autrement que par « 75018 ». Le 18e va de la Butte à la Porte de la Chapelle :
# un bien invérifiable peut être n'importe où, et ce sont justement les
# quartiers bon marché qui affichent les plus fortes marges. Sans cette
# pénalité, le haut du classement leur revenait mécaniquement.
#
# Le choix est de rétrograder plutôt que d'exclure : quelques-unes de ces
# annonces sont réellement sur la Butte, elles restent donc consultables.
PENALITE_LOCALISATION = float(os.getenv("PENALITE_LOCALISATION", "20"))


def _penalite_localisation(annonce):
    return 0 if localisation_verifiee(annonce) else PENALITE_LOCALISATION


def calculer_score(annonce, zone="montmartre", score_ml=0):
    """
    `score_ml` est accepté mais ignoré : la composante de préférences apprises
    est retirée du classement. Le paramètre reste dans la signature pour ne pas
    casser l'appel de main.py, et pour pouvoir la réintroduire sans effort le
    jour où assez de likes et dislikes auront été enregistrés.
    """
    texte = " ".join(str(annonce.get(c) or "") for c in ("titre", "description"))

    score = (
        _points_fraicheur(int(annonce.get("jours_en_ligne") or 0))
        + _points_marge(float(annonce.get("marge_pct") or 0))
        + _points_decote(
            float(annonce.get("prix_m2") or 0),
            float(annonce.get("prix_m2_ref") or parametres_zone(zone)[0]),
        )
        + _points_travaux(annonce.get("dpe"), texte)
        + _points_baisses(int(annonce.get("nb_baisses") or 0))
        - _penalite_localisation(annonce)
    )
    return max(0, min(int(round(score)), 100))
