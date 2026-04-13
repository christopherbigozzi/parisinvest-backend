import hashlib
from supabase import create_client
from config import SUPABASE_URL, SUPABASE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def generer_id(adresse, surface, prix):
    """Génère un ID unique pour dédupliquer les annonces."""
    # On arrondit le prix à ±5% pour matcher les doublons
    prix_arrondi = round(prix / 5000) * 5000
    cle = f"{adresse.lower().strip()}-{surface}-{prix_arrondi}"
    return hashlib.md5(cle.encode()).hexdigest()

def sauvegarder_annonce(annonce):
    """Sauvegarde une annonce, met à jour si elle existe déjà."""
    annonce_id = generer_id(
        annonce.get("adresse", ""),
        annonce.get("surface", 0),
        annonce.get("prix", 0)
    )
    annonce["id"] = annonce_id

    # Vérifier si l'annonce existe déjà
    existant = supabase.table("annonces").select("id, prix").eq("id", annonce_id).execute()

    if existant.data:
        # L'annonce existe — on vérifie si le prix a changé (baisse)
        ancien_prix = existant.data[0]["prix"]
        if annonce["prix"] < ancien_prix:
            # Enregistrer la baisse dans l'historique
            supabase.table("historique_prix").insert({
                "annonce_id": annonce_id,
                "prix": ancien_prix
            }).execute()
            print(f"  Baisse de prix détectée : {ancien_prix} → {annonce['prix']} €")

        # Mettre à jour l'annonce
        supabase.table("annonces").update({
            "prix": annonce["prix"],
            "prix_m2": annonce["prix_m2"],
            "score": annonce["score"],
            "marge_nette": annonce["marge_nette"],
            "marge_pct": annonce["marge_pct"],
            "date_maj": "now()"
        }).eq("id", annonce_id).execute()
    else:
        # Nouvelle annonce — on l'insère
        supabase.table("annonces").insert(annonce).execute()
        print(f"  Nouvelle annonce : {annonce['titre']} — {annonce['prix']} €")

def get_top_annonces(zone="montmartre", limite=5):
    """Récupère les meilleures annonces par score."""
    result = supabase.table("annonces")\
        .select("*")\
        .eq("zone", zone)\
        .eq("actif", True)\
        .order("score", desc=True)\
        .limit(limite)\
        .execute()
    return result.data

def get_historique_prix(annonce_id):
    """Récupère l'historique des baisses de prix d'une annonce."""
    result = supabase.table("historique_prix")\
        .select("prix, date_obs")\
        .eq("annonce_id", annonce_id)\
        .order("date_obs")\
        .execute()
    return result.data
