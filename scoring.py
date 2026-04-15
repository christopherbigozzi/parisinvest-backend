from config import (TRAVAUX_PAR_M2, FRAIS_NOTAIRE, ZONES)

PRIX_REVENTE_M2_HAUT = 13500


def calculer_marge(surface, prix_achat):
    """
    Marge nette :
      Prix revente (13 500 euro/m2) - Achat - Travaux - Notaire (8%)
    """
    travaux      = surface * TRAVAUX_PAR_M2
    notaire      = prix_achat * FRAIS_NOTAIRE
    prix_revente = surface * PRIX_REVENTE_M2_HAUT
    cout_total   = prix_achat + travaux + notaire
    marge_nette  = prix_revente - cout_total
    marge_pct    = (marge_nette / cout_total) * 100 if cout_total > 0 else 0
    return round(marge_nette), round(marge_pct, 1)


def calculer_score(annonce, zone="montmartre", score_ml=0):
    """
    Score sur 100 pts :
      1. Fraicheur annonce       : 20 pts
      2. Marge nette             : 25 pts
      3. Decote vs prix DVF      : 15 pts
      4. Prix/m2 vs moyenne      : 15 pts
      5. Potentiel travaux (DPE) : 5 pts
      6. Score ML (preferences)  : 25 pts (0 si < 3 feedbacks)
    Bonus baisses de prix        : +5 pts max
    """
    score    = 0
    prix_ref = ZONES.get(zone, {}).get("prix_m2_ref", 9800)
    prix_m2  = annonce.get("prix_m2", 0) or 0
    marge_pct = annonce.get("marge_pct", 0) or 0
    jours    = annonce.get("jours_en_ligne", 0) or 0
    baisses  = annonce.get("nb_baisses", 0) or 0
    dpe      = str(annonce.get("dpe", "") or "").upper().strip()

    # ── 1. Fraicheur (20 pts) ─────────────────────────────────────────────────
    if jours == 0:
        score += 20
    elif jours <= 1:
        score += 18
    elif jours <= 3:
        score += 14
    elif jours <= 7:
        score += 9
    elif jours <= 14:
        score += 5
    elif jours <= 30:
        score += 2

    # ── 2. Marge nette (25 pts) ───────────────────────────────────────────────
    if marge_pct >= 30:
        score += 25
    elif marge_pct >= 25:
        score += 21
    elif marge_pct >= 20:
        score += 17
    elif marge_pct >= 15:
        score += 12
    elif marge_pct >= 10:
        score += 7
    elif marge_pct >= 5:
        score += 3
    elif marge_pct > 0:
        score += 1

    # ── 3. Decote vs marche (15 pts) ─────────────────────────────────────────
    if prix_ref > 0 and prix_m2 > 0:
        decote = (prix_ref - prix_m2) / prix_ref
        if decote >= 0.20:
            score += 15
        elif decote >= 0.15:
            score += 12
        elif decote >= 0.10:
            score += 8
        elif decote >= 0.05:
            score += 4
        elif decote >= 0:
            score += 1

    # ── 4. Prix/m2 vs moyenne (15 pts) ───────────────────────────────────────
    if prix_m2 > 0 and prix_ref > 0:
        if prix_m2 < prix_ref * 0.80:
            score += 15
        elif prix_m2 < prix_ref * 0.88:
            score += 10
        elif prix_m2 < prix_ref * 0.95:
            score += 5
        elif prix_m2 < prix_ref:
            score += 2

    # ── 5. Potentiel travaux DPE (5 pts) ─────────────────────────────────────
    dpe_points = {"G": 5, "F": 4, "E": 3, "D": 2, "C": 1, "B": 0, "A": 0}
    score += dpe_points.get(dpe, 2)

    # ── 6. Score ML preferences (25 pts) ─────────────────────────────────────
    score += min(int(score_ml or 0), 25)

    # ── Bonus baisses (+5 pts max) ────────────────────────────────────────────
    if baisses >= 3:
        score += 5
    elif baisses == 2:
        score += 3
    elif baisses == 1:
        score += 1

    return min(score, 100)
