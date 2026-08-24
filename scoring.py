"""
scoring.py — modèle de marge et score d'opportunité.

Marge AVANT FISCALITÉ. Le régime d'imposition se traite au cas par cas sur
les annonces retenues, il n'entre pas dans le classement.

Répartition du score, sur 100 :
    fraîcheur de l'annonce ....... 10
    marge nette .................. 45
    décote vs prix de marché ..... 30
    potentiel travaux ............ 15
    bonus baisses de prix ........ +5, plafonné à 100
    localisation invérifiable .... −20

Rééquilibrage du 19/08/2026, à la demande. Le prix au m² et le potentiel
travaux montent, la fraîcheur descend de 20 à 10 : elle pesait autant que la
moitié de la marge, ce qui a du sens en location où tout se joue en heures,
beaucoup moins en achat-revente où une annonce de quatre jours reste une
bonne affaire. La marge cède 5 points au profit de la décote.

Les composantes « décote vs DVF » et « prix/m² vs moyenne » d'une version
antérieure mesuraient la même chose ; elles sont fusionnées en une seule.

Les préférences apprises (ML) ont été retirées : sans like ni dislike
enregistré, elles valaient zéro pour toute annonce, ce qui plafonnait le score
réel à 75 — exactement la valeur de SCORE_ALERTE, rendant l'alerte
inatteignable.

Conséquence à connaître : marge et décote sont, à surface donnée, deux
fonctions du prix au m². Elles pèsent 75 points à elles deux, donc le
classement suit très largement le prix au m². C'est assumé et voulu.
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


def texte_annonce(annonce):
    """Titre et description réunis, seule matière disponible pour les mots-clés."""
    return " ".join(str(annonce.get(c) or "") for c in ("titre", "description"))


def detecter_travaux(annonce):
    """
    Le bien est-il à retravailler ? Vrai quand le DPE est mauvais (F ou G) ou
    quand le vocabulaire de l'annonce le dit.

    Sert deux usages d'un même verdict : la composante de score, et le repère
    affiché au dashboard. Une seule règle, un seul endroit.
    """
    dpe = str(annonce.get("dpe") or "").upper().strip()[:1]
    if dpe in ("F", "G"):
        return True
    if dpe in ("A", "B"):
        return False

    texte = texte_annonce(annonce)
    if MOTS_REFAIT.search(texte):
        return False
    return bool(MOTS_TRAVAUX.search(texte))


def mots_travaux_trouves(annonce):
    """Les termes qui ont déclenché le repère, pour pouvoir l'expliquer."""
    texte = texte_annonce(annonce)
    if MOTS_REFAIT.search(texte):
        return []
    vus, ordre = set(), []
    for m in MOTS_TRAVAUX.finditer(texte):
        mot = m.group(1).lower()
        if mot not in vus:
            vus.add(mot)
            ordre.append(mot)
    return ordre[:4]


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
    """10 points. En achat-revente, quatre jours d'ancienneté ne disqualifient
    pas une affaire — ce critère ne doit pas écraser le prix au m²."""
    for seuil, pts in ((0, 10), (1, 9), (3, 7), (7, 5), (14, 3), (30, 1)):
        if jours <= seuil:
            return pts
    return 0


def _points_marge(marge_pct):
    """45 points, mêmes paliers."""
    for seuil, pts in ((30, 45), (25, 38), (20, 31), (15, 22), (10, 13), (5, 5)):
        if marge_pct >= seuil:
            return pts
    return 2 if marge_pct > 0 else 0


def _points_decote(prix_m2, prix_ref):
    if not (prix_m2 > 0 and prix_ref > 0):
        return 0
    decote = (prix_ref - prix_m2) / prix_ref
    for seuil, pts in ((0.25, 30), (0.20, 25), (0.15, 20), (0.10, 14), (0.05, 7)):
        if decote >= seuil:
            return pts
    return 3 if decote >= 0 else 0


def _points_travaux(dpe, texte):
    """
    15 points au maximum. C'est sur le bien à retravailler que se fait la
    marge : ce critère pèse désormais autant qu'un tiers de la décote.

    Le DPE reste le signal le plus fiable quand il existe. À défaut — et
    c'est le cas de toutes les annonces SeLoger, dont la page est
    inatteignable — on lit le vocabulaire du titre et de la description.
    """
    dpe = str(dpe or "").upper().strip()[:1]
    pts_dpe = {"G": 15, "F": 12, "E": 9, "D": 6, "C": 3}.get(dpe)
    if pts_dpe is not None:
        return pts_dpe
    if dpe in ("A", "B"):
        return 0

    texte = texte or ""
    if MOTS_REFAIT.search(texte):
        return 0
    if MOTS_TRAVAUX.search(texte):
        return 15
    return 6  # information absente : note neutre, ni prime ni pénalité


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
