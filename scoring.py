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


def calculer_score(annonce, zone="montmartre"):
    """
    Score sur 120 pts ramene a 100 :
      1. Fraicheur annonce           : 25 pts  (forte ponderation nouvelles)
      2. Marge nette                 : 30 pts
      3. Decote vs prix DVF          : 20 pts
      4. Prix/m2 vs moyenne          : 15 pts
      5. Potentiel travaux (DPE)     : 10 pts
    Bonus baisses de prix            : +5 pts max (hors total)
    """
    score    = 0
    prix_ref = ZONES.get(zone, {}).get("prix_m2_ref", 9800)
    prix_m2  = annonce.get("prix_m2", 0) or 0
    marge_pct = annonce.get("marge_pct", 0) or 0
    jours    = annonce.get("jours_en_ligne", 0) or 0
    baisses  = annonce.get("nb_baisses", 0) or 0
    dpe      = str(annonce.get("dpe", "") or "").upper().strip()

    # ── 1. Fraicheur (25 pts) ─────────────────────────────────────────────────
    # Forte prime aux nouvelles annonces — tu dois etre le premier
    if jours == 0:
        score += 25    # publiee aujourd hui
    elif jours <= 1:
        score += 23    # hier
    elif jours <= 3:
        score += 18    # moins de 3 jours
    elif jours <= 7:
        score += 12    # moins d une semaine
    elif jours <= 14:
        score += 7     # moins de 2 semaines
    elif jours <= 30:
        score += 3     # moins d un mois
    else:
        score += 0     # vieille annonce — pas de bonus fraicheur

    # ── 2. Marge nette (30 pts) ───────────────────────────────────────────────
    if marge_pct >= 30:
        score += 30
    elif marge_pct >= 25:
        score += 26
    elif marge_pct >= 20:
        score += 21
    elif marge_pct >= 15:
        score += 15
    elif marge_pct >= 10:
        score += 9
    elif marge_pct >= 5:
        score += 4
    elif marge_pct > 0:
        score += 1

    # ── 3. Decote vs marche (20 pts) ─────────────────────────────────────────
    if prix_ref > 0 and prix_m2 > 0:
        decote = (prix_ref - prix_m2) / prix_ref
        if decote >= 0.20:
            score += 20
        elif decote >= 0.15:
            score += 16
        elif decote >= 0.10:
            score += 11
        elif decote >= 0.05:
            score += 6
        elif decote >= 0:
            score += 2

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

    # ── 5. Potentiel travaux DPE (10 pts) ────────────────────────────────────
    dpe_points = {"G": 10, "F": 9, "E": 6, "D": 3, "C": 1, "B": 0, "A": 0}
    score += dpe_points.get(dpe, 4)

    # ── Bonus baisses de prix (+5 pts max) ───────────────────────────────────
    # Signal fort de vendeur motive
    if baisses >= 3:
        score += 5
    elif baisses == 2:
        score += 3
    elif baisses == 1:
        score += 1

    return min(score, 100)
