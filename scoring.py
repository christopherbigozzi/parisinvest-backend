from config import (TRAVAUX_PAR_M2, FRAIS_NOTAIRE, DUREE_PORTAGE,
                     FRAIS_AGENCE, PRIX_REVENTE_M2, ZONES)

def calculer_marge(surface, prix_achat):
    """Calcule la marge nette réelle après tous les frais."""
    travaux      = surface * TRAVAUX_PAR_M2
    notaire      = prix_achat * FRAIS_NOTAIRE
    portage      = prix_achat * 0.01 * (DUREE_PORTAGE / 12)
    prix_revente = surface * PRIX_REVENTE_M2
    agence       = prix_revente * FRAIS_AGENCE
    cout_total   = prix_achat + travaux + notaire + portage + agence
    marge_nette  = prix_revente - cout_total
    marge_pct    = (marge_nette / cout_total) * 100 if cout_total > 0 else 0
    return round(marge_nette), round(marge_pct, 1)

def calculer_score(annonce, zone="montmartre"):
    """
    Score sur 100 selon 5 critères :
      - Décote vs prix DVF zone      : 35 pts
      - DPE F/G (potentiel réno)     : 20 pts
      - Ancienneté + baisses de prix : 20 pts
      - Prix/m² vs moyenne zone      : 15 pts
      - Marge nette                  : 10 pts
    """
    score = 0
    prix_ref = ZONES.get(zone, {}).get("prix_m2_ref", 9800)

    # 1. Décote vs marché (35 pts)
    prix_m2 = annonce.get("prix_m2", 0)
    if prix_m2 > 0:
        decote = (prix_ref - prix_m2) / prix_ref
        if decote >= 0.20:
            score += 35
        elif decote >= 0.15:
            score += 28
        elif decote >= 0.10:
            score += 20
        elif decote >= 0.05:
            score += 12
        elif decote >= 0:
            score += 5

    # 2. DPE (20 pts) — F/G = max car forte revalorisation post-réno
    dpe = annonce.get("dpe", "").upper()
    dpe_points = {"G": 20, "F": 18, "E": 12, "D": 8, "C": 4, "B": 2, "A": 0}
    score += dpe_points.get(dpe, 0)

    # 3. Ancienneté + baisses de prix (20 pts)
    jours = annonce.get("jours_en_ligne", 0)
    baisses = annonce.get("nb_baisses", 0)
    if jours >= 90:
        score += 10
    elif jours >= 60:
        score += 7
    elif jours >= 30:
        score += 4
    elif jours >= 14:
        score += 2
    score += min(baisses * 4, 10)  # max 10 pts pour les baisses

    # 4. Prix/m² vs moyenne (15 pts)
    if prix_m2 > 0 and prix_m2 < prix_ref * 0.85:
        score += 15
    elif prix_m2 < prix_ref * 0.92:
        score += 10
    elif prix_m2 < prix_ref:
        score += 5

    # 5. Marge nette (10 pts)
    marge_pct = annonce.get("marge_pct", 0)
    if marge_pct >= 20:
        score += 10
    elif marge_pct >= 15:
        score += 8
    elif marge_pct >= 10:
        score += 5
    elif marge_pct >= 5:
        score += 2

    return min(score, 100)
