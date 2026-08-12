"""
tests_integration.py — cycle complet sans réseau ni base.

Gmail, Supabase, Telegram et les appels HTTP d'enrichissement sont remplacés
par des doublures. Le mail injecté est un vrai mail Bien'ici archivé, donc ce
qui est vérifié ici est bien la chaîne réelle : lecture → parsing → filtre de
zone → marge → score → écriture.

    python tests_integration.py
"""
import os
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "cle-de-test")

echecs = []


def affirmer(intitule, condition, detail=""):
    if condition:
        print(f"  ok   {intitule}")
    else:
        print(f"  ÉCHEC {intitule} {detail}")
        echecs.append(intitule)


def verifier(intitule, obtenu, attendu):
    affirmer(intitule, obtenu == attendu, f"\n         attendu : {attendu!r}"
                                          f"\n         obtenu  : {obtenu!r}")


# ─── Doublures des dépendances absentes du conteneur ────────────────────────
def _module(nom, **attributs):
    mod = types.ModuleType(nom)
    for cle, val in attributs.items():
        setattr(mod, cle, val)
    sys.modules[nom] = mod
    return mod


class _Planificateur:
    def every(self, *a, **k):
        return self

    minutes = property(lambda self: self)

    def do(self, *a, **k):
        return self

    def run_pending(self):
        pass


_module("schedule", every=lambda *a, **k: _Planificateur(), run_pending=lambda: None)


class _Table:
    """Table Supabase en mémoire, suffisante pour ce que le code appelle."""

    def __init__(self, magasin, nom):
        self.magasin, self.nom = magasin, nom
        self._filtres, self._charge, self._action = [], None, None

    def select(self, *a, **k): self._action = "select"; return self
    def insert(self, charge):  self._action, self._charge = "insert", charge; return self
    def update(self, charge):  self._action, self._charge = "update", charge; return self
    def eq(self, col, val):   self._filtres.append(("eq", col, val)); return self
    def in_(self, col, vals): self._filtres.append(("in", col, list(vals))); return self
    def lte(self, col, val):  self._filtres.append(("lte", col, val)); return self
    def gt(self, col, val):   self._filtres.append(("gt", col, val)); return self
    def lt(self, col, val):   self._filtres.append(("lt", col, val)); return self
    def order(self, *a, **k): return self
    def limit(self, *a): return self

    def execute(self):
        lignes = self.magasin.setdefault(self.nom, [])
        if self._action == "insert":
            charges = self._charge if isinstance(self._charge, list) else [self._charge]
            lignes.extend(charges)
            return types.SimpleNamespace(data=charges)
        if self._action == "update":
            touchees = [l for l in lignes if self._correspond(l)]
            for l in touchees:
                l.update(self._charge)
            return types.SimpleNamespace(data=touchees)
        return types.SimpleNamespace(data=[l for l in lignes if self._correspond(l)])

    def _correspond(self, ligne):
        for operateur, col, val in self._filtres:
            presente = ligne.get(col)
            if operateur == "eq" and presente != val:
                return False
            if operateur == "in" and presente not in val:
                return False
            if operateur in ("lte", "gt", "lt"):
                if presente is None:
                    return False
                try:
                    gauche, droite = float(presente), float(val)
                except (TypeError, ValueError):
                    continue
                if operateur == "lte" and not gauche <= droite:
                    return False
                if operateur == "gt" and not gauche > droite:
                    return False
                if operateur == "lt" and not gauche < droite:
                    return False
        return True


class _Supabase:
    def __init__(self):
        self.magasin = {}

    def table(self, nom):
        return _Table(self.magasin, nom)


_faux_supabase = _Supabase()
_module("supabase", create_client=lambda *a, **k: _faux_supabase)

_module("google")
_module("google.oauth2")
_module("google.oauth2.credentials", Credentials=object)
_module("googleapiclient")
_module("googleapiclient.discovery", build=lambda *a, **k: None)
_module("googleapiclient.errors", HttpError=type("HttpError", (Exception,), {}))

# ─── Import du code réel ────────────────────────────────────────────────────
import main
import gmail_client
import enricher
import database

FIXTURE = Path(__file__).parent / "tests" / "fixtures" / "bienici_2026-08-12.txt"

mails_marques = []

main.gmail_client.recuperer_alertes = lambda **k: [{
    "id": "mail-test-1",
    "source": "bienici",
    "sujet": "L'agence Junot Abbesses a sélectionné pour vous ces annonces",
    "expediteur": "no_reply@bienici.com",
    "date": datetime.now(timezone.utc),
    "html": "",
    "texte": FIXTURE.read_text(encoding="utf-8"),
}]
main.gmail_client.marquer_lot_traite = lambda ids: mails_marques.extend(ids)

# L'enrichissement sortirait sur le réseau : on simule un DPE trouvé.
def _faux_enrichir(annonces, maximum=25):
    for a in annonces:
        a.setdefault("dpe", "")
        if not a["dpe"]:
            a["dpe"] = "F"
            a["description"] = "Appartement à rénover, beau potentiel, dans son jus."
    return annonces


main.enrichir_lot = _faux_enrichir
main.get_preference_vectors = lambda: (None, None, 0, 0)
main.calculer_score_ml = lambda *a, **k: 0

alertes_envoyees = []
main.envoyer_alerte = lambda a: (alertes_envoyees.append(a) or True)
main.start_proxy_thread = lambda: None
main.verifier_urls_mortes = lambda *a, **k: None


print("\n── Cycle complet sur un mail Bien'ici réel ──────────────────────")
main.run()

annonces = _faux_supabase.magasin.get("annonces", [])
verifier("trois annonces en base", len(annonces), 3)

if len(annonces) == 3:
    par_surface = {round(float(a["surface"])): a for a in annonces}

    affirmer("les trois surfaces attendues sont présentes",
             set(par_surface) == {31, 46, 128}, f"-> {sorted(par_surface)}")

    petit = par_surface.get(31)
    if petit:
        verifier("prix conservé", float(petit["prix"]), 389000.0)
        verifier("zone renseignée", petit["zone"], "montmartre")
        affirmer("identifiant non vide", bool(petit.get("id")))
        affirmer("empreinte non vide", bool(petit.get("empreinte")))
        affirmer("score calculé et borné",
                 0 <= (petit.get("score") or 0) <= 100, f"-> {petit.get('score')}")
        affirmer("postes de coût détaillés présents",
                 all(petit.get(c) for c in ("travaux", "notaire", "portage",
                                            "prix_revente", "cout_total")))
        affirmer("annonce marquée active", petit.get("actif") is True)

    affirmer("les identifiants sont tous distincts",
             len({a["id"] for a in annonces}) == 3)
    affirmer("aucune marge fantaisiste",
             all(-3_000_000 < float(a["marge_nette"]) < 3_000_000 for a in annonces))

    cher = par_surface.get(128)
    if cher:
        affirmer("le 128 m² à 1,495 M€ ressort en marge négative",
                 float(cher["marge_nette"]) < 0,
                 f"-> {cher['marge_nette']:,} €")

verifier("le mail est marqué traité", mails_marques, ["mail-test-1"])

print("\n── Le mail n'est pas retraité au cycle suivant ──────────────────")
avant = len(_faux_supabase.magasin.get("annonces", []))
main.gmail_client.recuperer_alertes = lambda **k: []
main.run()
verifier("aucune ligne ajoutée", len(_faux_supabase.magasin.get("annonces", [])), avant)

print("\n" + "=" * 64)
if echecs:
    print(f"{len(echecs)} test(s) en échec : " + ", ".join(echecs))
    sys.exit(1)
print("Le cycle complet fonctionne.")
