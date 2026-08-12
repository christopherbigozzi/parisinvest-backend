"""
tests_unitaires.py — vérification des fonctions pures, sans réseau ni base.

    python tests_unitaires.py
"""
import os
import sys

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "cle-de-test")

from dedup import (normaliser_url, id_annonce, empreinte, similarite_titre,
                   meme_bien, grouper)
from scoring import calculer_marge, calculer_score, _points_travaux
from enricher import extraire_dpe, extraire_etage, extraire_pieces

echecs = []


def verifier(intitule, obtenu, attendu):
    if obtenu == attendu:
        print(f"  ok   {intitule}")
    else:
        print(f"  ÉCHEC {intitule}\n         attendu : {attendu!r}\n         obtenu  : {obtenu!r}")
        echecs.append(intitule)


def affirmer(intitule, condition, detail=""):
    if condition:
        print(f"  ok   {intitule}")
    else:
        print(f"  ÉCHEC {intitule} {detail}")
        echecs.append(intitule)


print("\n── Normalisation d'URL ──────────────────────────────────────────")
verifier(
    "retire les paramètres de tracking",
    normaliser_url("https://www.seloger.com/annonces/123.htm?utm_source=mail&cmpid=x"),
    "https://seloger.com/annonces/123.htm",
)
verifier(
    "conserve les paramètres signifiants",
    normaliser_url("https://www.bienici.com/annonce?id=ABC123&utm_medium=email"),
    "https://bienici.com/annonce?id=ABC123",
)
affirmer(
    "deux variantes de la même URL donnent le même id",
    id_annonce("seloger", url="https://www.seloger.com/a/1.htm?utm_source=mail")
    == id_annonce("seloger", url="http://seloger.com/a/1.htm/?fbclid=zz"),
)

print("\n── Le bug de fusion corrigé ─────────────────────────────────────")
a = {"titre": "Appartement 2 pièces avec balcon rue Lepic", "surface": 30,
     "prix": 450000, "pieces": 2, "adresse": "Paris 18e"}
b = {"titre": "Studio rénové vue Sacré-Coeur", "surface": 30,
     "prix": 450000, "pieces": 1, "adresse": "Paris 18e"}
affirmer(
    "deux biens distincts de même surface et prix ne fusionnent plus",
    not meme_bien(a, b),
    "-> ils sont considérés identiques, la correction ne tient pas",
)
affirmer(
    "leurs id sont bien différents",
    id_annonce("seloger", url="https://seloger.com/a/1.htm")
    != id_annonce("seloger", url="https://seloger.com/a/2.htm"),
)

print("\n── Regroupement du même bien entre portails ─────────────────────")
sel = {"titre": "Appartement 3 pièces rue Caulaincourt balcon", "surface": 62,
       "prix": 690000, "pieces": 3, "adresse": "Paris 18e"}
bie = {"titre": "Vente appartement 3 pièces Caulaincourt avec balcon", "surface": 62,
       "prix": 685000, "pieces": 3, "adresse": "Paris 18e"}
affirmer("le même bien sur deux portails est reconnu", meme_bien(sel, bie))
affirmer(
    "et partage la même empreinte malgré 5 000 € d'écart",
    empreinte(62, 690000, 3) == empreinte(62, 685000, 3),
    f"-> {empreinte(62, 690000, 3)} vs {empreinte(62, 685000, 3)}",
)
affirmer(
    "des surfaces différentes ne partagent pas l'empreinte",
    empreinte(62, 690000, 3) != empreinte(70, 690000, 3),
)
affirmer(
    "un écart de prix important casse le rapprochement",
    not meme_bien(sel, {**bie, "prix": 610000}),
)
affirmer(
    "un nombre de pièces différent aussi",
    not meme_bien(sel, {**bie, "pieces": 4}),
)
affirmer(
    "similarité de titre cohérente",
    similarite_titre(sel["titre"], bie["titre"]) >= 0.45,
    f"-> {similarite_titre(sel['titre'], bie['titre']):.2f}",
)

print("\n── Regroupement d'un lot ────────────────────────────────────────")
lot = [
    {"id": "s1", "titre": "Appartement 3 pièces rue Caulaincourt balcon",
     "surface": 62, "prix": 690000, "pieces": 3, "adresse": "Paris 18e", "source": "seloger"},
    {"id": "b1", "titre": "Vente appartement 3 pièces Caulaincourt avec balcon",
     "surface": 62, "prix": 685000, "pieces": 3, "adresse": "Paris 18e", "source": "bienici"},
    {"id": "j1", "titre": "Trois pièces lumineux avenue Junot terrasse",
     "surface": 62, "prix": 880000, "pieces": 3, "adresse": "Paris 18e", "source": "jinka"},
    {"id": "s2", "titre": "Studio rue Lepic à rénover",
     "surface": 26, "prix": 295000, "pieces": 1, "adresse": "Paris 18e", "source": "seloger"},
]
for a in lot:
    a["empreinte"] = empreinte(a["surface"], pieces=a["pieces"])

groupes = grouper(lot)
verifier("le lot se réduit à 3 biens distincts", len(groupes), 3)
affirmer(
    "les deux publications du bien Caulaincourt sont réunies",
    any({m["id"] for m in g} == {"s1", "b1"} for g in groupes),
    f"-> {[sorted(m['id'] for m in g) for g in groupes]}",
)
affirmer(
    "le bien Junot reste seul malgré la même surface",
    any({m["id"] for m in g} == {"j1"} for g in groupes),
)

print("\n── Modèle de marge ──────────────────────────────────────────────")
m = calculer_marge(surface=40, prix_achat=380000)
affirmer("tous les postes sont renseignés",
         all(m[c] > 0 for c in ("travaux", "notaire", "portage",
                                "frais_revente", "prix_revente", "cout_total")))
verifier("travaux = 40 m² x 1200 €", m["travaux"], 48000)
verifier("notaire = 8 % de 380 000 €", m["notaire"], 30400)
affirmer("le coût total dépasse le prix d'achat",
         m["cout_total"] > 380000 + 48000 + 30400,
         "-> le portage et les frais de revente ne sont pas comptés")
affirmer("marge cohérente avec les postes",
         m["marge_nette"] == m["prix_revente"] - m["cout_total"])
affirmer("un bien hors de prix ressort en marge négative",
         calculer_marge(40, 700000)["marge_nette"] < 0)
verifier("surface nulle ne fait pas planter", calculer_marge(0, 300000)["marge_nette"], 0)

print("\n── Score ────────────────────────────────────────────────────────")
excellente = {"titre": "Appartement à rénover, dans son jus", "surface": 45,
              "prix": 340000, "prix_m2": 7556, "prix_m2_ref": 10100,
              "marge_pct": 32, "jours_en_ligne": 0, "nb_baisses": 2, "dpe": "F"}
mediocre = {"titre": "Superbe appartement refait à neuf", "surface": 45,
            "prix": 620000, "prix_m2": 13778, "prix_m2_ref": 10100,
            "marge_pct": -12, "jours_en_ligne": 60, "nb_baisses": 0, "dpe": "B"}
s_exc, s_med = calculer_score(excellente), calculer_score(mediocre)
affirmer(f"la bonne affaire score haut ({s_exc}/100)", s_exc >= 75)
affirmer(f"la mauvaise score bas ({s_med}/100)", s_med <= 20)
affirmer("le score reste borné à 100",
         calculer_score({**excellente, "nb_baisses": 9}, score_ml=25) <= 100)
affirmer("une annonce vide ne fait pas planter", 0 <= calculer_score({}) <= 100)

print("\n── Potentiel travaux ────────────────────────────────────────────")
verifier("DPE G prime au maximum", _points_travaux("G", ""), 5)
verifier("DPE B ne rapporte rien", _points_travaux("B", ""), 0)
verifier("sans DPE, le vocabulaire travaux prime",
         _points_travaux("", "Appartement à rénover entièrement"), 5)
verifier("sans DPE, un bien refait à neuf ne rapporte rien",
         _points_travaux("", "Superbe bien refait à neuf"), 0)
verifier("sans information, note neutre", _points_travaux("", "Bel appartement"), 2)

print("\n── Extraction depuis la page de l'annonce ───────────────────────")
verifier("DPE lu dans le texte",
         extraire_dpe("Chauffage collectif. DPE : F. GES : C."), "F")
verifier("classe énergie reconnue",
         extraire_dpe("Classe énergétique D, consommation 250 kWh"), "D")
verifier("absence de DPE renvoie une chaîne vide",
         extraire_dpe("Appartement lumineux proche métro"), "")
verifier("étage numérique", extraire_etage("Situé au 4ème étage avec ascenseur"), "4e")
verifier("rez-de-chaussée", extraire_etage("Appartement en rez-de-chaussée"), "RDC")
verifier("nombre de pièces", extraire_pieces("Bel appartement 3 pièces de 62 m²"), 3)

print("\n" + "=" * 64)
if echecs:
    print(f"{len(echecs)} test(s) en échec : " + ", ".join(echecs))
    sys.exit(1)
print("Tous les tests passent.")
