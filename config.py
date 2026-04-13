# ============================================================
# CONFIG — mets tes vraies clés ici (ou dans Railway en vars)
# ============================================================

SUPABASE_URL = "https://bhyexniwpnfvylndqexm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJoeWV4bml3cG5mdnlsbmRxZXhtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzYxMDI0MzIsImV4cCI6MjA5MTY3ODQzMn0.qKuPSyd_FfCcdMdeRSh3t577g-bsA7swT6xpL2cm7ew"

# Jinka API — crée ton compte sur jinka.fr et mets ta clé ici
JINKA_API_KEY = "METS_TA_CLE_JINKA_ICI"

# Telegram — tu l'auras après avoir créé le bot avec @BotFather
TELEGRAM_BOT_TOKEN = "METS_TON_TOKEN_TELEGRAM_ICI"
TELEGRAM_CHAT_ID   = "METS_TON_CHAT_ID_ICI"

# Score minimum pour déclencher une alerte Telegram
SCORE_ALERTE = 75

# Paramètres de marge (identiques au dashboard)
TRAVAUX_PAR_M2   = 1200   # €/m²
FRAIS_NOTAIRE    = 0.08   # 8%
DUREE_PORTAGE    = 12     # mois
FRAIS_AGENCE     = 0.03   # 3%
PRIX_REVENTE_M2  = 11500  # €/m² estimé après réno

# Zone Montmartre — polygone approximatif (lat/lng)
ZONES = {
    "montmartre": {
        "cp": ["75018"],
        "mots_cles": ["montmartre", "abbesses", "lepic", "caulaincourt",
                      "damremont", "lamarck", "clignancourt", "marcadet",
                      "clichy", "pigalle", "barbes"],
        "prix_m2_ref": 9800,   # prix moyen DVF 18e
    }
}
