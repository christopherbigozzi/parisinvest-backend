import os

# ─────────────────────────────────────────────────────────
# Ces valeurs sont lues depuis les variables Railway
# Ne jamais écrire les vraies clés ici directement
# ─────────────────────────────────────────────────────────

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://bhyexniwpnfvylndqexm.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJoeWV4bml3cG5mdnlsbmRxZXhtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYxMDI0MzIsImV4cCI6MjA5MTY3ODQzMn0.qKuPSyd_FfCcdMdeRSh3t577g-bsA7swT6xpL2cm7ew")

# LeBonCoin API partenaire — demande à partenaires@leboncoin.fr
# Laisser vide tant que tu n'as pas la clé, le scraper continue sans LBC
LBC_API_KEY = os.getenv("LBC_API_KEY", "")

# Telegram bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Score minimum pour déclencher une alerte Telegram
SCORE_ALERTE = 75

# ─────────────────────────────────────────────────────────
# Paramètres de marge (identiques au dashboard)
# ─────────────────────────────────────────────────────────
TRAVAUX_PAR_M2  = 1200   # €/m²
FRAIS_NOTAIRE   = 0.08   # 8%
DUREE_PORTAGE   = 12     # mois
FRAIS_AGENCE    = 0.03   # 3%
PRIX_REVENTE_M2 = 11500  # €/m² estimé après réno haut de gamme

# ─────────────────────────────────────────────────────────
# Zones géographiques
# ─────────────────────────────────────────────────────────
ZONES = {
    "montmartre": {
        "cp":          ["75018"],
        "mots_cles":   ["montmartre", "abbesses", "lepic", "caulaincourt",
                        "damremont", "lamarck", "clignancourt", "marcadet",
                        "clichy", "pigalle", "barbes"],
        "prix_m2_ref": 9800,   # prix médian DVF 18e (mis à jour dynamiquement)
    }
}
