"""
gmail_client.py — lecture des alertes immobilières dans Gmail via l'API.

Le worker ne lit que le label `parisinvest`. Une fois un mail parsé, il reçoit
le label `parisinvest/traite` : c'est ce qui évite de le retraiter à chaque
cycle sans avoir à toucher au statut lu/non lu, que l'utilisateur manipule
de son côté.

Authentification : OAuth avec un refresh token obtenu une seule fois via
authorize_gmail.py, puis stocké dans les variables Railway.
"""
import base64
import re
from email.utils import parsedate_to_datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import (
    GMAIL_CLIENT_ID,
    GMAIL_CLIENT_SECRET,
    GMAIL_REFRESH_TOKEN,
    GMAIL_LABEL,
    GMAIL_LABEL_TRAITE,
)

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES    = ["https://www.googleapis.com/auth/gmail.modify"]

# Correspondance expéditeur → source. L'ordre compte : le premier motif qui
# matche gagne, donc les motifs les plus spécifiques d'abord.
SOURCES = [
    ("jinka",     re.compile(r"@(?:\w+\.)?jinka\.fr",       re.I)),
    ("seloger",   re.compile(r"@(?:\w+\.)?seloger\.com",    re.I)),
    ("leboncoin", re.compile(r"@(?:\w+\.)?leboncoin\.fr",   re.I)),
    ("bienici",   re.compile(r"@(?:\w+\.)?bienici\.com",    re.I)),
    ("pap",       re.compile(r"@(?:\w+\.)?pap\.fr",         re.I)),
]

# Mails transactionnels à ignorer : confirmations de compte, mots de passe,
# newsletters. Ils portent le bon expéditeur mais ne contiennent aucune annonce.
SUJETS_IGNORES = re.compile(
    r"(confirm|vérifi|verifi|bienvenue|welcome|mot de passe|password|"
    r"code de connexion|votre compte|désinscri|desinscri|newsletter|"
    r"a bien été créé|conditions générales)",
    re.I,
)


class GmailIndisponible(RuntimeError):
    pass


def _service():
    if not (GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN):
        raise GmailIndisponible(
            "Identifiants Gmail absents. Définir GMAIL_CLIENT_ID, "
            "GMAIL_CLIENT_SECRET et GMAIL_REFRESH_TOKEN."
        )
    creds = Credentials(
        token=None,
        refresh_token=GMAIL_REFRESH_TOKEN,
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        token_uri=TOKEN_URI,
        scopes=SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _id_label(svc, nom, creer=True):
    """Retourne l'ID d'un label, en le créant au besoin."""
    labels = svc.users().labels().list(userId="me").execute().get("labels", [])
    for lab in labels:
        if lab["name"].lower() == nom.lower():
            return lab["id"]
    if not creer:
        return None
    cree = svc.users().labels().create(
        userId="me",
        body={
            "name": nom,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ).execute()
    print(f"  [Gmail] Label créé : {nom}")
    return cree["id"]


def _decoder(donnees):
    if not donnees:
        return ""
    manque = len(donnees) % 4
    if manque:
        donnees += "=" * (4 - manque)
    try:
        return base64.urlsafe_b64decode(donnees).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extraire_corps(payload):
    """
    Descend récursivement dans les parties MIME et retourne (html, texte).
    Les alertes immo sont quasiment toujours en multipart/alternative avec
    une version HTML riche et une version texte pauvre — on privilégie le HTML.
    """
    html, texte = "", ""

    def parcourir(part):
        nonlocal html, texte
        mime = part.get("mimeType", "")
        corps = part.get("body", {}) or {}
        donnees = corps.get("data")

        if mime == "text/html" and donnees and not html:
            html = _decoder(donnees)
        elif mime == "text/plain" and donnees and not texte:
            texte = _decoder(donnees)

        for sous in part.get("parts", []) or []:
            parcourir(sous)

    parcourir(payload)
    return html, texte


def _entete(headers, nom):
    for h in headers:
        if h.get("name", "").lower() == nom.lower():
            return h.get("value", "")
    return ""


def identifier_source(expediteur):
    for nom, motif in SOURCES:
        if motif.search(expediteur or ""):
            return nom
    return None


def recuperer_alertes(limite=100, inclure_traites=False):
    """
    Retourne la liste des mails d'alerte non encore traités.

    Chaque entrée : {id, source, sujet, expediteur, date, html, texte}
    Les mails transactionnels (confirmations, codes) sont écartés ici, pas
    plus loin dans la chaîne — inutile de les faire traverser les parsers.
    """
    svc = _service()

    id_label  = _id_label(svc, GMAIL_LABEL, creer=False)
    if not id_label:
        print(f"  [Gmail] Label '{GMAIL_LABEL}' introuvable — aucune alerte à lire.")
        return []

    id_traite = _id_label(svc, GMAIL_LABEL_TRAITE, creer=True)

    requete = f"label:{GMAIL_LABEL}"
    if not inclure_traites:
        requete += f" -label:{GMAIL_LABEL_TRAITE}"

    messages, page_token = [], None
    while len(messages) < limite:
        rep = svc.users().messages().list(
            userId="me",
            q=requete,
            maxResults=min(100, limite - len(messages)),
            pageToken=page_token,
        ).execute()
        messages += rep.get("messages", [])
        page_token = rep.get("nextPageToken")
        if not page_token:
            break

    print(f"  [Gmail] {len(messages)} mail(s) à traiter sous '{GMAIL_LABEL}'")

    alertes = []
    for meta in messages:
        try:
            msg = svc.users().messages().get(
                userId="me", id=meta["id"], format="full"
            ).execute()
        except HttpError as e:
            print(f"  [Gmail] Lecture impossible {meta['id']} : {e}")
            continue

        payload    = msg.get("payload", {}) or {}
        headers    = payload.get("headers", []) or []
        expediteur = _entete(headers, "From")
        sujet      = _entete(headers, "Subject")
        date_brute = _entete(headers, "Date")

        source = identifier_source(expediteur)
        if not source:
            print(f"  [Gmail] Expéditeur inconnu, ignoré : {expediteur}")
            continue

        if SUJETS_IGNORES.search(sujet or ""):
            print(f"  [Gmail] Mail transactionnel ignoré : {sujet[:60]}")
            marquer_traite(svc, meta["id"], id_traite)
            continue

        html, texte = _extraire_corps(payload)
        if not (html or texte):
            print(f"  [Gmail] Corps vide : {sujet[:60]}")
            marquer_traite(svc, meta["id"], id_traite)
            continue

        try:
            recu = parsedate_to_datetime(date_brute) if date_brute else None
        except Exception:
            recu = None

        alertes.append({
            "id":         meta["id"],
            "source":     source,
            "sujet":      sujet,
            "expediteur": expediteur,
            "date":       recu,
            "html":       html,
            "texte":      texte,
        })

    print(f"  [Gmail] {len(alertes)} alerte(s) exploitable(s)")
    return alertes


def marquer_traite(svc, id_message, id_label_traite):
    try:
        svc.users().messages().modify(
            userId="me",
            id=id_message,
            body={"addLabelIds": [id_label_traite]},
        ).execute()
        return True
    except HttpError as e:
        print(f"  [Gmail] Marquage impossible {id_message} : {e}")
        return False


def marquer_lot_traite(ids_messages):
    """Marque une série de mails comme traités, en un seul appel."""
    if not ids_messages:
        return
    svc = _service()
    id_traite = _id_label(svc, GMAIL_LABEL_TRAITE, creer=True)
    try:
        svc.users().messages().batchModify(
            userId="me",
            body={"ids": list(ids_messages), "addLabelIds": [id_traite]},
        ).execute()
        print(f"  [Gmail] {len(ids_messages)} mail(s) marqué(s) traité(s)")
    except HttpError as e:
        print(f"  [Gmail] Marquage par lot impossible : {e}")


def tester_connexion():
    """Vérifie que les identifiants fonctionnent. Retourne l'adresse du compte."""
    svc = _service()
    profil = svc.users().getProfile(userId="me").execute()
    return profil.get("emailAddress", "")
