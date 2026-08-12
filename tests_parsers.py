"""
tests_parsers.py — vérification des parseurs sur des mails réels archivés.

Chaque fichier de tests/fixtures/ est un corps de mail authentique. Quand un
portail change la mise en forme de ses alertes, on ajoute le nouveau mail en
fixture plutôt que de corriger à l'aveugle.

    python tests_parsers.py
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "cle-de-test")

from parsers import parser_alerte

FIXTURES = Path(__file__).parent / "tests" / "fixtures"
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


def charger(nom, source):
    return {
        "id": "test-" + nom,
        "source": source,
        "sujet": nom,
        "expediteur": f"no_reply@{source}.com",
        "date": datetime(2026, 8, 12, 9, 19, tzinfo=timezone.utc),
        "html": "",
        "texte": (FIXTURES / nom).read_text(encoding="utf-8"),
    }


print("\n── Bien'ici — mail du 12/08/2026 ────────────────────────────────")
annonces = parser_alerte(charger("bienici_2026-08-12.txt", "bienici"))

verifier("trois annonces extraites", len(annonces), 3)

if len(annonces) == 3:
    a1, a2, a3 = annonces

    verifier("annonce 1 — surface", a1["surface"], 31.0)
    verifier("annonce 1 — prix", a1["prix"], 389000.0)
    verifier("annonce 1 — pièces", a1["pieces"], 2)
    verifier("annonce 1 — prix au m²", a1["prix_m2"], 12548)
    verifier("annonce 1 — titre", a1["titre"], "Appartement 2 pièces 31 m²")
    verifier("annonce 1 — adresse", a1["adresse"], "75018 Paris 18e")
    verifier("annonce 1 — référence", a1["ref_source"], "3583ABBDOR")
    affirmer("annonce 1 — URL du portail",
             a1["url"].startswith("https://www.bienici.com/annonce/apimo-86344937"),
             f"-> {a1['url'][:70]}")
    affirmer("annonce 1 — photo rattachée",
             a1["photo"] and "apimo-86344937" in a1["photo"],
             f"-> {a1['photo']}")

    verifier("annonce 2 — surface", a2["surface"], 46.0)
    verifier("annonce 2 — prix", a2["prix"], 600000.0)
    verifier("annonce 2 — référence composée", a2["ref_source"], "3139MONREI/3710ABB")

    verifier("annonce 3 — surface", a3["surface"], 128.0)
    verifier("annonce 3 — prix à sept chiffres", a3["prix"], 1495000.0)
    verifier("annonce 3 — pièces", a3["pieces"], 5)
    affirmer("annonce 3 — photo distincte de l'annonce 1",
             a3["photo"] != a1["photo"])

    affirmer("les photos ne sont jamais celles de l'agence",
             all("5528f3ca" not in (a.get("photo") or "") for a in annonces))
    affirmer("le lien « Voir tous les biens de l'agence » n'est pas pris "
             "pour une annonce",
             all("annonces-apimo-6612" not in a["url"] for a in annonces))
    affirmer("le numéro de téléphone de l'agence n'est pas lu comme un prix",
             all(a["prix"] >= 30000 for a in annonces))
    affirmer("chaque annonce a un identifiant distinct",
             len({a["ident"] for a in annonces}) == 3)
    affirmer("la date de publication reprend la date du mail",
             all(a["date_publi"].startswith("2026-08-12") for a in annonces))

print("\n── Robustesse ───────────────────────────────────────────────────")
vide = {"id": "x", "source": "bienici", "sujet": "vide", "date": None,
        "html": "", "texte": ""}
verifier("un mail vide ne produit rien", parser_alerte(vide), [])

sans_lien = {**vide, "texte": "Bonjour, voici votre récapitulatif hebdomadaire."}
verifier("un mail sans annonce ne produit rien", parser_alerte(sans_lien), [])

inconnu = {**vide, "source": "unportailinconnu", "texte": "peu importe"}
verifier("un portail non géré ne fait pas planter", parser_alerte(inconnu), [])

print("\n" + "=" * 64)
if echecs:
    print(f"{len(echecs)} test(s) en échec : " + ", ".join(echecs))
    sys.exit(1)
print("Tous les tests de parsing passent.")
