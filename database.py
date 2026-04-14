import hashlib
import requests
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def generer_id(adresse, surface, prix):
    prix_arrondi = round(prix / 5000) * 5000
    cle = f"{adresse.lower().strip()}-{surface}-{prix_arrondi}"
    return hashlib.md5(cle.encode()).hexdigest()


def verifier_annonce_en_ligne(url):
    """Verifie si une annonce est encore accessible en ligne."""
    if not url:
        return True
    try:
        resp = requests.head(url, timeout=8, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code in (404, 410, 301):
            return False
        return True
    except Exception:
        return True


def desactiver_annonces_expirees():
    """
    Verifie toutes les annonces actives et desactive celles
    dont l URL ne repond plus (404/410).
    Lance un echantillon de 50 annonces par cycle pour ne pas surcharger.
    """
    print("  [Check] Verification annonces expirees...")
    try:
        result = supabase.table("annonces")\
            .select("id, url, titre")\
            .eq("actif", True)\
            .not_.is_("url", "null")\
            .neq("url", "")\
            .order("date_maj", desc=False)\
            .limit(50)\
            .execute()

        annonces = result.data or []
        desactivees = 0

        for a in annonces:
            if not verifier_annonce_en_ligne(a.get("url", "")):
                supabase.table("annonces")\
                    .update({"actif": False})\
                    .eq("id", a["id"])\
                    .execute()
                desactivees += 1
                print(f"  [Check] Expiree : {a.get('titre', '')[:50]}")

        print(f"  [Check] {len(annonces)} verifiees, {desactivees} desactivees")

    except Exception as e:
        print(f"  [Check] Erreur : {e}")


def sauvegarder_annonce(annonce):
    """Sauvegarde une annonce, met a jour si elle existe deja."""
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
                "prix": ancien_prix
            }).execute()
            print(f"  Baisse detectee : {ancien_prix} -> {annonce['prix']} EUR")

        supabase.table("annonces").update({
            "prix":       annonce["prix"],
            "prix_m2":    annonce["prix_m2"],
            "score":      annonce["score"],
            "marge_nette": annonce["marge_nette"],
            "marge_pct":  annonce["marge_pct"],
            "photo":      annonce.get("photo"),
            "actif":      True,
            "date_maj":   "now()"
        }).eq("id", annonce_id).execute()
    else:
        supabase.table("annonces").insert(annonce).execute()
        print(f"  Nouvelle annonce : {annonce['titre']} — {annonce['prix']} EUR")


def get_top_annonces(zone="montmartre", limite=5):
    result = supabase.table("annonces")\
        .select("*")\
        .eq("zone", zone)\
        .eq("actif", True)\
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
