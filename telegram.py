"""
telegram.py — notification des opportunités.

Retourne True si le message est parti, pour que l'appelant n'enregistre
l'alerte que lorsqu'elle a réellement été délivrée.
"""
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCORE_ALERTE

EMOJI_DPE = {"G": "🟠", "F": "🟠", "E": "🟡", "D": "🟢", "C": "🟢", "B": "🟢", "A": "🟢"}


def _euros(valeur):
    return f"{float(valeur or 0):,.0f}".replace(",", " ") + " €"


def envoyer_alerte(annonce):
    if (annonce.get("score") or 0) < SCORE_ALERTE:
        return False

    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("  [Telegram] Identifiants absents, alerte non envoyée")
        return False

    score = annonce.get("score") or 0
    dpe = str(annonce.get("dpe") or "").upper()[:1]

    lignes = [
        f"{'🔥' if score >= 85 else '⭐'} *Score {score}/100*",
        "",
        f"🏠 {annonce.get('titre', 'Sans titre')}",
        f"📍 {annonce.get('adresse', 'Paris 18e')}"
        + (f" · {annonce['etage']}" if annonce.get("etage") else ""),
        f"📐 {float(annonce.get('surface') or 0):.0f} m²"
        + (f" · {annonce['pieces']} pièces" if annonce.get("pieces") else ""),
        f"💰 {_euros(annonce.get('prix'))} "
        f"({_euros(annonce.get('prix_m2'))}/m²)",
    ]

    if dpe:
        lignes.append(f"{EMOJI_DPE.get(dpe, '⚪')} DPE {dpe}")

    if annonce.get("nb_baisses"):
        lignes.append(f"↘️ {annonce['nb_baisses']} baisse(s) de prix depuis la mise en ligne")

    lignes += [
        "",
        "*Marge avant fiscalité*",
        f"Travaux : {_euros(annonce.get('travaux'))}",
        f"Notaire : {_euros(annonce.get('notaire'))}",
        f"Portage : {_euros(annonce.get('portage'))}",
        f"Revente estimée : {_euros(annonce.get('prix_revente'))}",
        f"*Marge nette : {_euros(annonce.get('marge_nette'))} "
        f"({float(annonce.get('marge_pct') or 0):.1f} %)*",
        "",
        f"📡 {annonce.get('source', '?')} · [Voir l'annonce]({annonce.get('url', '')})",
    ]

    try:
        rep = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": "\n".join(lignes),
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=10,
        )
        if rep.status_code == 200:
            print(f"  [Telegram] Alerte envoyée : {annonce.get('titre', '')[:45]}")
            return True
        print(f"  [Telegram] Erreur {rep.status_code} : {rep.text[:160]}")
    except Exception as e:
        print(f"  [Telegram] Exception : {e}")
    return False
