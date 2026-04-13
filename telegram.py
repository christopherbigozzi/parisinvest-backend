import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCORE_ALERTE

def envoyer_alerte(annonce):
    """Envoie une alerte Telegram pour une bonne opportunité."""
    if annonce["score"] < SCORE_ALERTE:
        return

    emoji_score = "🔥" if annonce["score"] >= 85 else "⭐"
    emoji_dpe = {"G": "🟠", "F": "🟡", "E": "🟡", "D": "🟢"}.get(
        annonce.get("dpe", ""), "⚪"
    )

    msg = (
        f"{emoji_score} *Nouvelle opportunité — Score {annonce['score']}/100*\n\n"
        f"🏠 {annonce['titre']}\n"
        f"📍 {annonce['adresse']}\n"
        f"💰 {int(annonce['prix']):,} € "
        f"({int(annonce['prix_m2']):,} €/m²)\n"
        f"📐 {annonce['surface']} m²\n"
        f"{emoji_dpe} DPE {annonce.get('dpe', 'NC')}\n\n"
        f"📊 *Calcul de marge*\n"
        f"Marge nette : {int(annonce['marge_nette']):,} €\n"
        f"Rendement : {annonce['marge_pct']:.1f}%\n\n"
        f"🔗 [Voir l'annonce]({annonce['url']})\n"
        f"📡 Source : {annonce['source']}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"  Alerte Telegram envoyée : {annonce['titre']}")
        else:
            print(f"  Telegram erreur {resp.status_code} : {resp.text}")
    except Exception as e:
        print(f"  Telegram exception : {e}")
