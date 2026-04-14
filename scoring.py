from config import (TRAVAUX_PAR_M2, FRAIS_NOTAIRE, ZONES)

PRIX_REVENTE_M2_HAUT = 13500


def calculer_marge(surface, prix_achat):
    """
    Marge nette simplifiee :
      Prix revente (13 500 euro/m2 fourchette haute)
      - Prix achat
      - Travaux (1 200 euro/m2)
      - Frais notaire (8%)
    Sans portage ni frais agence revente.
    """
    travaux      = surface * TRAVAUX_PAR_M2
    notaire      = prix_achat * FRAIS_NOTAIRE
    prix_revente = surface * PRIX_REVENTE_M2_HAUT
    cout_total   = prix_achat + travaux + notaire
    marge_nette  = prix_revente - cout_total
    marge_pct    = (marge_nette / cout_total) * 100 if cout_total > 0 else 0
    return round(marge_nette), round(marge_pct, 1)


def calculer_score(annonce, zone="montmartre"):
    """
    Score sur 100 :
      1. Marge nette                     : 30 pts
      2. Decote vs prix DVF zone         : 25 pts
      3. Anciennete + baisses de prix    : 15 pts
      4. Prix/m2 vs moyenne zone         : 15 pts
      5. Potentiel travaux (DPE + etat)  : 15 pts
    """
    score     = 0
    prix_ref  = ZONES.get(zone, {}).get("prix_m2_ref", 9800)
    prix_m2   = annonce.get("prix_m2", 0) or 0
    marge_pct = annonce.get("marge_pct", 0) or 0
    jours     = annonce.get("jours_en_ligne", 0) or 0
    baisses   = annonce.get("nb_baisses", 0) or 0
    dpe       = str(annonce.get("dpe", "") or "").upper().strip()

    # 1. Marge nette (30 pts)
    if marge_pct >= 25:
        score += 30
    elif marge_pct >= 20:
        score += 25
    elif marge_pct >= 15:
        score += 20
    elif marge_pct >= 10:
        score += 13
    elif marge_pct >= 5:
        score += 7
    elif marge_pct > 0:
        score += 3

    # 2. Decote vs marche (25 pts)
    if prix_ref > 0 and prix_m2 > 0:
        decote = (prix_ref - prix_m2) / prix_ref
        if decote >= 0.20:
            score += 25
        elif decote >= 0.15:
            score += 20
        elif decote >= 0.10:
            score += 14
        elif decote >= 0.05:
            score += 8
        elif decote >= 0:
            score += 3

    # 3. Anciennete + baisses (15 pts)
    # 5 pts nouvelles (<=3j) OU vieilles (>=60j) + 5 pts baisses + 5 pts combo
    if jours <= 3:
        score += 5
    elif jours >= 90:
        score += 5
    elif jours >= 60:
        score += 3
    score += min(baisses * 2, 5)
    if baisses >= 2 and jours >= 30:
        score += 5

    # 4. Prix/m2 vs moyenne (15 pts)
    if prix_m2 > 0 and prix_ref > 0:
        if prix_m2 < prix_ref * 0.80:
            score += 15
        elif prix_m2 < prix_ref * 0.88:
            score += 10
        elif prix_m2 < prix_ref * 0.95:
            score += 6
        elif prix_m2 < prix_ref:
            score += 3

    # 5. Potentiel travaux DPE (15 pts)
    dpe_points = {"G": 15, "F": 13, "E": 9, "D": 5, "C": 2, "B": 1, "A": 0}
    score += dpe_points.get(dpe, 6)

    return min(score, 100)
