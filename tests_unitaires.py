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
from enricher import (extraire_dpe, extraire_etage, extraire_pieces,
                      page_atteignable, appliquer_donnees_bienici,
                      _etage_depuis_json)
from parsers import surface_vendable
from zone_filter import est_dans_zone, localisation_verifiee

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

print("\n── Pages atteignables pour l'enrichissement ─────────────────────")
# Cycle du 17/08/2026 : les dix places d'enrichissement sont parties sur des
# liens de tracking SeLoger, tous en 403, pendant que les annonces Bien'ici —
# dont l'URL mène vraiment à la page — n'ont jamais eu leur tour.
verifier("une URL d'annonce Bien'ici est exploitable",
         page_atteignable({"url": "https://www.bienici.com/annonce/apimo-86344937"}),
         True)
verifier("une URL d'annonce SeLoger directe est exploitable",
         page_atteignable({"url": "https://www.seloger.com/annonces/123456789.htm"}),
         True)
verifier("un lien de tracking SeLoger est écarté",
         page_atteignable({"url": "https://click.by.seloger.com/?qs=ABB7InYiOjE"}),
         False)
verifier("une URL vide est écartée", page_atteignable({"url": ""}), False)
verifier("une annonce sans URL est écartée", page_atteignable({}), False)

print("\n── Fiche JSON Bien'ici ──────────────────────────────────────────")
# La page HTML de Bien'ici est une coquille JavaScript : rien à y lire. Son
# front s'alimente à realEstateAd.json, qui rend les mêmes champs sans script.
# Extrait réel de la fiche apimo-86344937, relevé le 17/08/2026.
FICHE = {
    "energyClassification": "G",
    "energyValue": 689,
    "greenhouseGazClassification": "C",
    "floor": 4,
    "floorQuantity": 5,
    "description": "Situé au cœur des Abbesses   dans une rue piétonne...",
    "surfaceArea": 30.5,
    "roomsQuantity": 2,
    "price": 389000,
}

a = {"dpe": "", "etage": None, "description": "", "pieces": 0}
verifier("la fiche renseigne quelque chose", appliquer_donnees_bienici(a, FICHE), True)
verifier("DPE repris de la fiche", a["dpe"], "G")
verifier("étage repris de la fiche", a["etage"], "4e")
verifier("pièces reprises de la fiche", a["pieces"], 2)
affirmer("description normalisée, sans espaces multiples",
         a["description"].startswith("Situé au cœur des Abbesses dans une rue"))

# Le mail fait foi sur ce qu'il a déjà donné : la fiche complète, elle n'écrase pas.
b = {"dpe": "D", "etage": "2e", "description": "déjà là", "pieces": 3}
appliquer_donnees_bienici(b, FICHE)
verifier("un DPE déjà connu n'est pas écrasé", b["dpe"], "D")
verifier("un étage déjà connu n'est pas écrasé", b["etage"], "2e")
verifier("des pièces déjà connues ne sont pas écrasées", b["pieces"], 3)

verifier("rez-de-chaussée", _etage_depuis_json(0), "RDC")
verifier("étage absent de la fiche", _etage_depuis_json(None), "")
verifier("une fiche vide ne renseigne rien", appliquer_donnees_bienici({}, {}), False)
verifier("une réponse inattendue ne fait pas planter",
         appliquer_donnees_bienici({}, "erreur"), False)

print("\n── Périmètre : la Butte stricte ─────────────────────────────────")
# Le 18e va de la Butte à la Porte de Clignancourt et à la Goutte d'Or, des
# marchés sans rapport. Comme le filtre acceptait tout ce qui portait 75018,
# les biens de ces quartiers, moins chers donc de meilleure marge apparente,
# occupaient les premières places du classement. Cas relevés le 17/08/2026.
CAS_ZONE = [
    # Hors périmètre
    ("Paris 19? Élégant 2/3 pièces avec fort potentiel", "75018 Paris 18e", False),
    ("Superbe 2P Paris 9ème arrondissement", "75018 Paris 18e", False),
    ("Appartement 75011 à rénover", "75018 Paris 18e", False),
    ("M° La Chapelle - 2 pièces 45m² (22m² LC)", "75018 Paris 18e", False),
    ("3P Paris 18e Marcadet Poissonniers", "75018 Paris 18e", False),
    ("COUP DE COEUR _ VILLAGE RAMEY", "75018 Paris 18e", False),
    ("Charmant 3 pièces - Lamarck / Caulaincourt",
     "Clignancourt-Jules Joffrin, 75018 Paris 18e", False),
    # Dans le périmètre
    ("PARIS 18 - Rue Muller, Appartement 2 pièces", "75018 Paris 18e", True),
    ("Un appartement au calme, en plein Montmartre", "75018 Paris 18e", True),
    ("Etage élevé avec ascenseur, vue Sacré Coeur",
     "Montmartre, 75018 Paris 18e", True),
    ("Appartement 2 pièces de 48 m² à rénover", "75018 Paris 18e", True),
    # Un nombre après « Paris » n'est pas toujours un arrondissement
    ("Bel appartement Paris 3 pièces plein sud",
     "Montmartre, 75018 Paris 18e", True),
    ("Appartement Paris 60 m² proche Abbesses",
     "Montmartre, 75018 Paris 18e", True),
]
for titre, adresse, attendu in CAS_ZONE:
    verifier(f"{'gardé ' if attendu else 'rejeté'} — {titre[:44]}",
             est_dans_zone({"titre": titre, "adresse": adresse}), attendu)

print("\n── Surface au sol contre surface Carrez ─────────────────────────")
# Seule la surface Carrez se vend. Les combles de la Butte en sont pleins :
# « 2 pièces 45m² (22m² LC) » affichait 87 % de marge sur 45 m², plus rien
# sur 22 — et trônait en tête du classement.
verifier("deux surfaces et mention LC : la plus petite gagne",
         surface_vendable("M° La Chapelle - 2 pièces 45m² (22m² LC)", 45.0), 22.0)
verifier("« au sol » face à « Carrez »",
         surface_vendable("Duplex 80 m² au sol, 62 m² Carrez", 80.0), 62.0)
verifier("une seule surface, déjà Carrez : inchangée",
         surface_vendable("EXCLUSIVITÉ - Rue Hermel - 39.57 m² LC", 39.57), 39.57)
verifier("sans mention Carrez, on ne touche à rien",
         surface_vendable("Appartement 3 pièces 58 m²", 58.0), 58.0)
verifier("deux surfaces sans mention : on ne devine pas",
         surface_vendable("Appartement 58 m² avec cave de 6 m²", 58.0), 58.0)

print("\n── Crible des quartiers exclus ──────────────────────────────────")
# Le crible passe avant tout, quartier annoncé compris : une annonce étiquetée
# « Montmartre » par SeLoger mais mentionnant Barbès doit sortir.
for titre, adresse in [
    ("Beau 2P proche Barbès-Rochechouart", "Montmartre, 75018 Paris 18e"),
    ("Studio MARX DORMOY rénové", "Montmartre, 75018 Paris 18e"),
    ("Appartement rue Marcadet", "Montmartre, 75018 Paris 18e"),
    ("M° La Chapelle - 2 pièces", "75018 Paris 18e"),
    ("3P Porte de Clignancourt", "75018 Paris 18e"),
    ("Charmant bien Château Rouge", "75018 Paris 18e"),
    ("Duplex rue du Poteau", "75018 Paris 18e"),
    ("2P square Léon, à rafraîchir", "75018 Paris 18e"),
    ("Bel appartement Guy Môquet", "75018 Paris 18e"),
]:
    verifier(f"rejeté — {titre[:44]}",
             est_dans_zone({"titre": titre, "adresse": adresse}), False)

# Les mots courants ne doivent pas déclencher le crible : une cave, une façade
# blanche ou une forêt n'ont rien à voir avec la rue Cavé ou la rue Blanche.
for titre, adresse in [
    ("Appartement avec cave et box, Abbesses", "Montmartre, 75018 Paris 18e"),
    ("Belle façade blanche, vue Sacré-Coeur", "Montmartre, 75018 Paris 18e"),
    ("F2 au pied du Sacré-Cœur", "Montmartre, 75018 Paris 18e"),
    ("PARIS 18 - Rue Muller, 2 pièces", "75018 Paris 18e"),
]:
    verifier(f"gardé — {titre[:44]}",
             est_dans_zone({"titre": titre, "adresse": adresse}), True)

print("\n── Score : marge à 50 points, ML retiré ─────────────────────────")
# Les 25 points de préférences apprises valaient zéro faute de like enregistré,
# ce qui plafonnait le score à 75 — la valeur même de SCORE_ALERTE. Leur poids
# est reporté sur la marge.
def _score_de(surface, prix, jours, titre="Appartement", dpe="",
              adresse="Montmartre, 75018 Paris 18e"):
    m = calculer_marge(surface, prix)
    return calculer_score({"titre": titre, "adresse": adresse, "description": "",
                           "jours_en_ligne": jours, "marge_pct": m["marge_pct"],
                           "prix_m2": m["prix_m2"], "prix_m2_ref": m["prix_m2_ref"],
                           "dpe": dpe, "nb_baisses": 0})

verifier("48 m² à 370 000 €, 3 jours, « à rénover »",
         _score_de(48.0, 370000, 3, "Appartement 2 pièces de 48 m² à rénover"), 82)
verifier("31 m² à 250 000 €, 3 jours", _score_de(31.0, 250000, 3), 71)
verifier("57 m² à 480 000 €, publié le jour même", _score_de(57.0, 480000, 0), 63)
affirmer("un score de 75 est désormais atteignable",
         _score_de(48.0, 370000, 3, "Appartement 2 pièces de 48 m² à rénover") >= 75)
affirmer("le score reste borné à 100",
         _score_de(30.0, 100000, 0, "Plateau à rénover, dans son jus", "G") <= 100)

print("\n── Pénalité de localisation invérifiable ────────────────────────")
# Les alertes SeLoger « exclusivités d'agence » ne donnent aucun quartier, ni
# rue, ni métro : impossible de distinguer la Butte de la Porte de la Chapelle.
# Comme les quartiers bon marché y sont surreprésentés, ces annonces montraient
# les meilleures marges et occupaient le haut du classement.
verifier("quartier nommé : localisation vérifiée",
         localisation_verifiee({"adresse": "Montmartre, 75018 Paris 18e"}), True)
verifier("rue de la Butte citée dans le titre : vérifiée",
         localisation_verifiee({"titre": "Paris 18ème Lamarck - 32m2 esprit loft",
                                "adresse": "75018 Paris 18e"}), True)
verifier("rue de la Butte citée dans la description : vérifiée",
         localisation_verifiee({"titre": "Appartement 4 pièces 76 m²",
                                "adresse": "75018 Paris 18e",
                                "description": "Montmartre / Rue Burq, balcon"}), True)
verifier("seulement « 75018 » : invérifiable",
         localisation_verifiee({"titre": "Appartement 2 pièces de 48 m² à rénover",
                                "adresse": "75018 Paris 18e"}), False)

sans_lieu = _score_de(48.0, 370000, 3, "Appartement 2 pièces de 48 m² à rénover",
                      adresse="75018 Paris 18e")
avec_lieu = _score_de(48.0, 370000, 3, "Appartement 2 pièces de 48 m² à rénover")
verifier("la pénalité vaut bien 20 points", avec_lieu - sans_lieu, 20)
affirmer("une annonce sans localisation ne franchit plus le seuil d'alerte",
         sans_lieu < 75)

print("\n" + "=" * 64)
if echecs:
    print(f"{len(echecs)} test(s) en échec : " + ", ".join(echecs))
    sys.exit(1)
print("Tous les tests passent.")
