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
    # Régression du 17/08/2026 : la photo était rattachée par position, or elle
    # précède le lien de son annonce dans le mail. Chaque annonce héritait donc
    # de la photo de la suivante, et la dernière n'en avait aucune.
    for rang, a in enumerate(annonces, start=1):
        affirmer(f"annonce {rang} — la photo est bien la sienne",
                 a["ident"] in (a.get("photo") or ""),
                 f"ident {a['ident']} absent de {a.get('photo')!r}")
    affirmer("le lien « Voir tous les biens de l'agence » n'est pas pris "
             "pour une annonce",
             all("annonces-apimo-6612" not in a["url"] for a in annonces))
    affirmer("le numéro de téléphone de l'agence n'est pas lu comme un prix",
             all(a["prix"] >= 30000 for a in annonces))
    affirmer("chaque annonce a un identifiant distinct",
             len({a["ident"] for a in annonces}) == 3)
    affirmer("la date de publication reprend la date du mail",
             all(a["date_publi"].startswith("2026-08-12") for a in annonces))

print("\n── SeLoger — mail du 17/08/2026, sans identifiant ───────────────")
# Tous les liens d'un mail SeLoger passent par click.by.seloger.com avec un
# jeton opaque : aucun identifiant d'annonce dans le corps, même encodé. Le
# découpage se fait donc sur l'en-tête « prix € prix/m² €/m² » et l'identité
# est forgée depuis le contenu.
#
# Fixture : mail authentique du 17/08/2026. Seuls les jetons de tracking ont
# été raccourcis, pour rester lisibles — le parseur ne s'appuie pas dessus.

sel = parser_alerte(charger("seloger_2026-08-17.txt", "seloger"))

verifier("trois annonces extraites", len(sel), 3)

if len(sel) == 3:
    s1, s2, s3 = sel

    verifier("annonce 1 — surface au centième", s1["surface"], 22.1)
    verifier("annonce 1 — prix", s1["prix"], 304000.0)
    verifier("annonce 1 — une pièce", s1["pieces"], 1)
    verifier("annonce 3 — surface au centième", s3["surface"], 55.17)
    verifier("annonce 3 — prix", s3["prix"], 599000.0)
    verifier("annonce 3 — trois pièces", s3["pieces"], 3)

    # SeLoger affiche lui-même le prix au m² : il doit retomber sur prix/surface.
    # C'est le contrôle le plus parlant sur ce parseur, il croise deux champs
    # lus séparément dans le mail.
    for rang, (a, attendu) in enumerate(zip(sel, (13756, 10865, 10857)), start=1):
        verifier(f"annonce {rang} — prix/m² conforme à celui annoncé",
                 round(a["prix"] / a["surface"]), attendu)

    affirmer("le quartier est repris dans l'adresse",
             s1["adresse"].startswith("Montmartre")
             and s3["adresse"].startswith("Clignancourt"))
    affirmer("le code postal est présent",
             all("75018" in a["adresse"] for a in sel))
    affirmer("les titres ne sont pas des libellés de pied de page",
             all("fréquence" not in a["titre"].lower()
                 and "confidentialité" not in a["titre"].lower() for a in sel))
    affirmer("chaque annonce a un identifiant distinct",
             len({a["ident"] for a in sel}) == 3)
    affirmer("l'URL reste cliquable même si elle est tracée",
             all(a["url"].startswith("https://click.by.seloger.com/") for a in sel))
    affirmer("le prix n'entre pas dans l'identifiant",
             all(str(int(a["prix"])) not in a["ident"] for a in sel))

    # Invariant décisif : le jeton de tracking change à chaque envoi. Si
    # l'identité en dépendait, chaque cycle créerait des doublons.
    renvoi = charger("seloger_2026-08-17.txt", "seloger")
    renvoi["texte"] = renvoi["texte"].replace("jeton", "AUTREJETON")
    sel_bis = parser_alerte(renvoi)
    verifier("un nouvel envoi du même mail donne les mêmes identifiants",
             [a["ident"] for a in sel_bis], [a["ident"] for a in sel])

print("\n── Choix du corps : texte vs HTML tracé ─────────────────────────")
# Régression du 17/08/2026. Le parseur gardait le corps le plus long, donc
# toujours le HTML — dont les liens passent par le traceur du portail, qui
# encode l'URL de destination. Résultat : 92 mails lus, 0 annonce extraite,
# alors que la version texte du même mail portait les liens en clair.
#
# Les URL ci-dessous sont celles d'un vrai mail Bien'ici du 17/08/2026 ;
# l'enrobage de tracking est reconstitué, Gmail ne restituant que le corps.

LIEN_CLAIR = "https://www.bienici.com/annonce/immo-facile-61357036"
LIEN_TRACE = ("https://mail-sender.bienici.com/c/click?u="
              "https%3A%2F%2Fwww.bienici.com%2Fannonce%2Fimmo-facile-61357036")

corps_texte = (
    f"Appartement 2 pièces 34 m²\n[{LIEN_CLAIR}]\n75018 Paris 18e\n"
    f"319 000 €\n[{LIEN_CLAIR}]\n"
)
# Volontairement plus long que la version texte, comme dans la réalité.
corps_html = (
    "<html><body><p>Bonne nouvelle, 1 nouvelle annonce correspond à votre "
    "alerte ! Gérez vos alertes, désinscription, mentions légales, "
    "conditions générales d'utilisation, politique de confidentialité.</p>"
    f"<a href=\"{LIEN_TRACE}\">Appartement 2 pièces 34 m²</a>"
    "<p>75018 Paris 18e</p>"
    f"<a href=\"{LIEN_TRACE}\">319 000 €</a></body></html>"
)

mail_mixte = {"id": "regression-17-08", "source": "bienici",
              "sujet": "1 nouvelle annonce pour « zone personnalisée »",
              "expediteur": "no_reply@bienici.com",
              "date": datetime(2026, 8, 17, 11, 50, tzinfo=timezone.utc),
              "html": corps_html, "texte": corps_texte}

resultat = parser_alerte(mail_mixte)
verifier("le corps texte est lu même quand le HTML est plus long",
         len(resultat), 1)
if resultat:
    verifier("identifiant du nouveau format d'agence",
             resultat[0]["ident"], "immo-facile-61357036")
    verifier("surface lue", resultat[0]["surface"], 34.0)
    verifier("prix lu", resultat[0]["prix"], 319000.0)

# Cas limite : le portail cesse d'envoyer une version texte. Le lien tracé
# doit alors être déplié pour rester exploitable.
mail_html_seul = {**mail_mixte, "id": "regression-html-seul", "texte": ""}
resultat_html = parser_alerte(mail_html_seul)
verifier("un lien tracé est déplié quand il n'y a que du HTML",
         len(resultat_html), 1)
if resultat_html:
    verifier("identifiant retrouvé dans le lien tracé",
             resultat_html[0]["ident"], "immo-facile-61357036")

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
