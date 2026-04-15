import os
import hashlib
import requests
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase     = create_client(SUPABASE_URL, SUPABASE_KEY)
MELO_API_KEY = os.getenv("MELO_API_KEY", "")
MELO_BASE    = "https://api.notif.immo/documents/properties"

MAX_JOURS    = 100  # Desactiver automatiquement au-dela de 100 jours


def generer_id(adresse, surface, prix):
    prix_arrondi = round(prix / 5000) * 5000
    cle = f"{adresse.lower().strip()}-{surface}-{prix_arrondi}"
    return hashlib.md5(cle.encode()).hexdigest()


def desactiver_annonces_expirees():
    """
    Triple vérification — 60 annonces par cycle, les plus anciennes en priorité :
    1. Ancienneté > 100 jours → désactivation immédiate sans vérification
    2. Melo expired=true → désactivation
    3. URL retourne 404/410 → désactivation
    """
    print("  [Check] Vérification annonces expirées...")
    try:
        # ── Etape 1 : désactiver toutes les annonces > 100 jours immédiatement ──
        result_old = supabase.table("annonces")\
            .update({"actif": False})\
            .eq("actif", True)\
            .lt("jours_en_ligne", 9999)\
            .gt("jours_en_ligne", MAX_JOURS)\
            .execute()
        nb_old = len(result_old.data) if result_old.data else 0
        if nb_old > 0:
            print(f"  [Check] {nb_old} annonces > {MAX_JOURS}j désactivées automatiquement")

        # ── Etape 2 : vérifier les 60 annonces actives les plus anciennes ────────
        result = supabase.table("annonces")\
            .select("id, url, titre, melo_id, jours_en_ligne")\
            .eq("actif", True)\
            .order("jours_en_ligne", desc=True)\
            .limit(60)\
            .execute()

        annonces    = result.data or []
        desactivees = 0

        for a in annonces:
            raison = _est_expiree(a)
            if raison:
                supabase.table("annonces")\
                    .update({"actif": False})\
                    .eq("id", a["id"])\
                    .execute()
                desactivees += 1
                print(f"  [Check] Désactivée ({raison}) : {a.get('titre','')[:50]}")

        print(f"  [Check] {len(annonces)} vérifiées, {desactivees} désactivées")

    except Exception as e:
        print(f"  [Check] Erreur : {e}")


def _est_expiree(a):
    """
    Retourne la raison d'expiration ou None si encore valide.
    """
    # Signal 1 : Melo a marqué le bien comme expired=true
    melo_id = a.get("melo_id") or ""
    if MELO_API_KEY and melo_id:
        try:
            resp = requests.get(
                MELO_BASE,
                params={"ids[]": melo_id, "expired": "true"},
                headers={"X-API-KEY": MELO_API_KEY},
                timeout=8
            )
            if resp.status_code == 200:
                total = resp.json().get("hydra:totalItems", -1)
                if total > 0:
                    return "Melo expired=true"
        except Exception:
            pass

    # Signal 2 : URL retourne 404 ou 410
    url = a.get("url") or ""
    if url:
        try:
            resp = requests.head(
                url, timeout=5, allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code in (404, 410):
                return f"URL {resp.status_code}"
        except Exception:
            pass

    return None


def sauvegarder_annonce(annonce):
    """Sauvegarde une annonce, met à jour si elle existe déjà."""
    # Rejeter les annonces trop vieilles avant même de les sauvegarder
    if (annonce.get("jours_en_ligne") or 0) > MAX_JOURS:
        return

    annonce_id = generer_id(
        annonce.get("adresse", ""),
        annonce.get("surface", 0),
        annonce.get("prix", 0)
    )
    annonce["id"] = annonce_id

    existant = supabase.table("annonces").select("id, prix").eq("id", annonce_id).execute()

    if existant.data:
        ancien_prix = existant.data[0]["prix"]
        if annonce["prix"] < ancien_prix:
            supabase.table("historique_prix").insert({
                "annonce_id": annonce_id,
                "prix":       ancien_prix
            }).execute()
            print(f"  Baisse détectée : {ancien_prix} → {annonce['prix']} €")

        supabase.table("annonces").update({
            "prix":           annonce["prix"],
            "prix_m2":        annonce["prix_m2"],
            "score":          annonce["score"],
            "marge_nette":    annonce["marge_nette"],
            "marge_pct":      annonce["marge_pct"],
            "photo":          annonce.get("photo"),
            "melo_id":        annonce.get("melo_id"),
            "jours_en_ligne": annonce.get("jours_en_ligne"),
            "actif":          True,
            "date_maj":       "now()"
        }).eq("id", annonce_id).execute()
    else:
        supabase.table("annonces").insert(annonce).execute()
        print(f"  Nouvelle annonce : {annonce['titre']} — {annonce['prix']} €")


def get_top_annonces(zone="montmartre", limite=5):
    result = supabase.table("annonces")\
        .select("*")\
        .eq("zone", zone)\
        .eq("actif", True)\
        .lte("jours_en_ligne", MAX_JOURS)\
        .order("score", desc=True)\
        .limit(limite)\
        .execute()
    return result.data


def get_historique_prix(annonce_id):
    result = supabase.table("historique_prix")\
        .select("prix, date_obs")\
        .eq("annonce_id", annonce_id)\
        .order("date_obs")\
        .execute()
    return result.data
