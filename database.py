"""
database.py — persistance Supabase.

Une ligne = une PUBLICATION (un portail donné). Les publications décrivant le
même bien partagent une `empreinte` ; à chaque cycle, une seule d'entre elles
est marquée `principal` et c'est celle que le dashboard affiche.
"""
from supabase import create_client

from config import SUPABASE_URL, SUPABASE_KEY, MAX_JOURS
from dedup import grouper

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Colonnes réellement présentes dans la table. Toute clé de travail ajoutée en
# cours de route (préfixée par _) est retirée avant écriture.
COLONNES = {
    "id", "empreinte", "principal", "titre", "description", "adresse", "surface",
    "pieces", "etage", "prix", "prix_m2", "prix_m2_ref", "dpe", "source", "url",
    "photo", "date_publi", "jours_en_ligne", "nb_baisses", "zone", "score",
    "marge_nette", "marge_pct", "travaux", "notaire", "portage", "frais_revente",
    "prix_revente", "cout_total", "actif", "gmail_id",
}


def _nettoyer(annonce):
    return {c: v for c, v in annonce.items() if c in COLONNES}


def desactiver_annonces_expirees():
    """
    Une annonce meurt de deux façons : elle dépasse MAX_JOURS, ou son URL
    ne répond plus. Le signal Melo a disparu avec l'API, il ne reste que
    ces deux-là.
    """
    print("  [Purge] Vérification des annonces expirées...")
    try:
        res = supabase.table("annonces") \
            .update({"actif": False}) \
            .eq("actif", True) \
            .gt("jours_en_ligne", MAX_JOURS) \
            .execute()
        nb = len(res.data) if res.data else 0
        if nb:
            print(f"  [Purge] {nb} annonce(s) au-delà de {MAX_JOURS} jours désactivée(s)")
    except Exception as e:
        print(f"  [Purge] Erreur : {e}")


def verifier_urls_mortes(limite=40):
    """
    Teste les URLs des annonces actives les plus anciennes. Volontairement
    limité : chaque vérification est une requête réseau vers un portail qui
    n'aime pas être sollicité en rafale.
    """
    import requests

    try:
        res = supabase.table("annonces") \
            .select("id, url, titre") \
            .eq("actif", True) \
            .order("jours_en_ligne", desc=True) \
            .limit(limite) \
            .execute()
    except Exception as e:
        print(f"  [Purge] Lecture impossible : {e}")
        return

    mortes = 0
    for a in res.data or []:
        url = a.get("url") or ""
        if not url:
            continue
        try:
            rep = requests.head(
                url, timeout=6, allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ParisInvest/1.0)"},
            )
            if rep.status_code in (404, 410):
                supabase.table("annonces").update({"actif": False}).eq("id", a["id"]).execute()
                mortes += 1
                print(f"  [Purge] Retirée ({rep.status_code}) : {a.get('titre','')[:50]}")
        except Exception:
            # Un timeout ne prouve rien : on laisse l'annonce active.
            continue

    print(f"  [Purge] {len(res.data or [])} URL(s) testée(s), {mortes} morte(s)")


def sauvegarder_annonce(annonce):
    """
    Insère ou met à jour une publication. Retourne "nouvelle", "maj" ou None.

    La baisse de prix est détectée ici : c'est le seul endroit qui voit
    l'ancien et le nouveau prix côte à côte.
    """
    if (annonce.get("jours_en_ligne") or 0) > MAX_JOURS:
        return None
    if not annonce.get("id"):
        print("  [Base] Annonce sans id, ignorée")
        return None

    try:
        existant = supabase.table("annonces") \
            .select("id, prix, nb_baisses") \
            .eq("id", annonce["id"]) \
            .execute()
    except Exception as e:
        print(f"  [Base] Lecture impossible : {e}")
        return None

    charge = _nettoyer(annonce)

    if existant.data:
        ancien = existant.data[0]
        ancien_prix = float(ancien.get("prix") or 0)
        nouveau_prix = float(annonce.get("prix") or 0)

        if nouveau_prix and ancien_prix and nouveau_prix < ancien_prix:
            try:
                supabase.table("historique_prix").insert({
                    "annonce_id": annonce["id"],
                    "prix": ancien_prix,
                }).execute()
            except Exception as e:
                print(f"  [Base] Historique non écrit : {e}")
            charge["nb_baisses"] = int(ancien.get("nb_baisses") or 0) + 1
            baisse = ancien_prix - nouveau_prix
            print(f"  [Base] Baisse de {baisse:,.0f} € : {annonce.get('titre','')[:45]}")

        charge["actif"] = True
        charge.pop("date_publi", None)  # la date de première publication ne bouge pas
        try:
            supabase.table("annonces").update(charge).eq("id", annonce["id"]).execute()
            return "maj"
        except Exception as e:
            print(f"  [Base] Mise à jour impossible : {e}")
            return None

    charge["actif"] = True
    charge.setdefault("nb_baisses", 0)
    try:
        supabase.table("annonces").insert(charge).execute()
        print(f"  [Base] Nouvelle : {annonce.get('titre','')[:45]} — "
              f"{float(annonce.get('prix') or 0):,.0f} €")
        return "nouvelle"
    except Exception as e:
        print(f"  [Base] Insertion impossible : {e}")
        return None


def recalculer_principaux(zone="montmartre"):
    """
    Dans chaque groupe d'empreinte, désigne la publication à afficher.

    On garde celle dont le prix est le plus bas — c'est celle que l'acheteur
    a intérêt à contacter — et à prix égal, la plus récente. Les autres
    restent en base pour l'historique mais sortent du dashboard.
    """
    try:
        res = supabase.table("annonces") \
            .select("id, empreinte, prix, surface, pieces, titre, adresse, "
                    "jours_en_ligne, principal") \
            .eq("zone", zone).eq("actif", True) \
            .execute()
    except Exception as e:
        print(f"  [Groupes] Lecture impossible : {e}")
        return

    groupes = grouper(res.data or [])

    a_activer, a_desactiver = [], []
    doublons = 0

    for membres in groupes:
        # À prix égal on garde la plus ancienne : c'est la publication
        # d'origine, celle dont l'historique de prix est le plus complet.
        gagnant = min(
            membres,
            key=lambda m: (float(m.get("prix") or 0), -int(m.get("jours_en_ligne") or 0)),
        )
        doublons += len(membres) - 1

        for m in membres:
            veut = (m["id"] == gagnant["id"])
            if bool(m.get("principal")) != veut:
                (a_activer if veut else a_desactiver).append(m["id"])

    for ids, valeur in ((a_activer, True), (a_desactiver, False)):
        if not ids:
            continue
        try:
            supabase.table("annonces").update({"principal": valeur}) \
                .in_("id", ids).execute()
        except Exception as e:
            print(f"  [Groupes] Mise à jour impossible : {e}")

    print(f"  [Groupes] {len(groupes)} bien(s) distinct(s), {doublons} doublon(s) masqué(s)")


def get_top_annonces(zone="montmartre", limite=10, principaux_seulement=True):
    requete = supabase.table("annonces").select("*") \
        .eq("zone", zone).eq("actif", True) \
        .lte("jours_en_ligne", MAX_JOURS)
    if principaux_seulement:
        requete = requete.eq("principal", True)
    return requete.order("score", desc=True).limit(limite).execute().data


def get_annonces_deja_alertees(ids):
    """Retourne les ids déjà notifiés, pour ne pas alerter deux fois."""
    if not ids:
        return set()
    try:
        res = supabase.table("alertes_envoyees").select("annonce_id") \
            .in_("annonce_id", list(ids)).execute()
        return {r["annonce_id"] for r in (res.data or [])}
    except Exception as e:
        print(f"  [Base] Lecture des alertes impossible : {e}")
        return set()


def enregistrer_alerte(annonce_id, score):
    try:
        supabase.table("alertes_envoyees").insert({
            "annonce_id": annonce_id, "score": score,
        }).execute()
    except Exception as e:
        print(f"  [Base] Alerte non enregistrée : {e}")


def get_historique_prix(annonce_id):
    return supabase.table("historique_prix") \
        .select("prix, date_obs").eq("annonce_id", annonce_id) \
        .order("date_obs").execute().data
