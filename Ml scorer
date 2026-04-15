"""
ml_scorer.py — Scoring ML basé sur les feedbacks utilisateur
Calcule un score de similarité entre une annonce et les préférences apprises.

Logique :
- On vectorise chaque annonce : [surface_norm, prix_m2_norm, dpe_num, marge_pct_norm, jours_norm]
- On calcule le vecteur moyen des "like" et des "dislike"
- Score ML = similarité cosinus avec les likes - similarité cosinus avec les dislikes
- Score ramené sur 25 points
"""
import os
import math
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Valeurs de normalisation (basées sur le marché Montmartre)
NORM = {
    "surface":        45.0,
    "prix_m2":     10000.0,
    "marge_pct":      30.0,
    "jours":          90.0,
}

DPE_NUM = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "": 4}


def vectoriser(surface, prix_m2, dpe, marge_pct, jours):
    """Transforme les caractéristiques d'une annonce en vecteur normalisé."""
    return [
        min(float(surface or 0) / NORM["surface"], 2.0),
        min(float(prix_m2 or 0) / NORM["prix_m2"], 2.0),
        DPE_NUM.get(str(dpe or "").upper(), 4) / 7.0,
        min(float(marge_pct or 0) / NORM["marge_pct"], 2.0),
        min(float(jours or 0) / NORM["jours"], 2.0),
    ]


def cosine_similarity(v1, v2):
    """Similarité cosinus entre deux vecteurs."""
    dot   = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)


def mean_vector(vectors):
    """Calcule le vecteur moyen d'une liste de vecteurs."""
    if not vectors:
        return None
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(len(vectors[0]))]


def get_preference_vectors():
    """
    Récupère les feedbacks depuis Supabase et calcule les vecteurs
    de préférence moyens pour les likes et dislikes.
    Retourne (vecteur_likes, vecteur_dislikes, nb_likes, nb_dislikes)
    """
    try:
        result = supabase.table("feedbacks")\
            .select("signal, surface, prix_m2, dpe, marge_pct, jours_en_ligne")\
            .execute()

        feedbacks = result.data or []
        if not feedbacks:
            return None, None, 0, 0

        likes    = [f for f in feedbacks if f["signal"] == "like"]
        dislikes = [f for f in feedbacks if f["signal"] == "dislike"]

        vecs_likes = [
            vectoriser(f["surface"], f["prix_m2"], f["dpe"], f["marge_pct"], f["jours_en_ligne"])
            for f in likes
        ]
        vecs_dislikes = [
            vectoriser(f["surface"], f["prix_m2"], f["dpe"], f["marge_pct"], f["jours_en_ligne"])
            for f in dislikes
        ]

        return (
            mean_vector(vecs_likes),
            mean_vector(vecs_dislikes),
            len(likes),
            len(dislikes)
        )

    except Exception as e:
        print(f"  [ML] Erreur get_preference_vectors : {e}")
        return None, None, 0, 0


def calculer_score_ml(annonce, vec_likes=None, vec_dislikes=None, nb_likes=0, nb_dislikes=0):
    """
    Calcule le score ML d'une annonce sur 25 points.

    - Si pas assez de données (< 3 likes) → 0 pts (on n'invente pas de préférences)
    - Sinon : score = (sim_likes - sim_dislikes) ramené sur [0, 25]
    """
    if nb_likes < 3 or vec_likes is None:
        return 0

    vec_annonce = vectoriser(
        annonce.get("surface", 0),
        annonce.get("prix_m2", 0),
        annonce.get("dpe", ""),
        annonce.get("marge_pct", 0),
        annonce.get("jours_en_ligne", 0),
    )

    sim_likes    = cosine_similarity(vec_annonce, vec_likes)
    sim_dislikes = cosine_similarity(vec_annonce, vec_dislikes) if vec_dislikes else 0

    # Score brut entre -1 et +1
    score_brut = sim_likes - (sim_dislikes * 0.7)

    # Ramener sur [0, 25]
    score_pts = max(0, min(25, round((score_brut + 1) / 2 * 25)))

    return score_pts


def enregistrer_feedback(annonce_id, signal, annonce):
    """Enregistre un feedback utilisateur (like ou dislike) dans Supabase."""
    try:
        supabase.table("feedbacks").insert({
            "annonce_id":    annonce_id,
            "signal":        signal,
            "surface":       annonce.get("surface"),
            "prix_m2":       annonce.get("prix_m2"),
            "dpe":           annonce.get("dpe", ""),
            "marge_pct":     annonce.get("marge_pct"),
            "jours_en_ligne": annonce.get("jours_en_ligne", 0),
            "nb_baisses":    annonce.get("nb_baisses", 0),
        }).execute()
        print(f"  [ML] Feedback '{signal}' enregistré pour {annonce_id}")
        return True
    except Exception as e:
        print(f"  [ML] Erreur enregistrement feedback : {e}")
        return False
