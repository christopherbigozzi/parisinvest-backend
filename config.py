"""
config.py — source de vérité unique des paramètres ParisInvest.

Aucune clé en dur : tout vient des variables d'environnement Railway.
Si une clé obligatoire manque, on plante au démarrage plutôt que de tourner
silencieusement sur une mauvaise config.
"""
import os


def _requis(nom):
    val = os.getenv(nom, "").strip()
    if not val:
        raise RuntimeError(
            f"Variable d'environnement manquante : {nom}. "
            f"À définir dans Railway → Variables."
        )
    return val


def _flottant(nom, defaut):
    try:
        return float(os.getenv(nom, "") or defaut)
    except ValueError:
        return defaut


# ─────────────────────────────────────────────────────────────────────────────
# Supabase
# ─────────────────────────────────────────────────────────────────────────────
SUPABASE_URL = _requis("SUPABASE_URL")

# Le worker écrit en base : il lui faut la clé service_role, pas la clé anon.
# La clé anon reste réservée au frontend, en lecture seule via les règles RLS.
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "").strip() or _requis("SUPABASE_KEY")

# ─────────────────────────────────────────────────────────────────────────────
# Gmail — sourcing par alertes mail
# ─────────────────────────────────────────────────────────────────────────────
GMAIL_CLIENT_ID     = os.getenv("GMAIL_CLIENT_ID", "").strip()
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN", "").strip()
GMAIL_LABEL         = os.getenv("GMAIL_LABEL", "parisinvest").strip()

# Label appliqué aux mails déjà traités, pour ne pas les reparser à chaque cycle.
GMAIL_LABEL_TRAITE  = os.getenv("GMAIL_LABEL_TRAITE", "parisinvest/traite").strip()

# ─────────────────────────────────────────────────────────────────────────────
# Telegram
# ─────────────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()
SCORE_ALERTE       = int(os.getenv("SCORE_ALERTE", "75"))

# ─────────────────────────────────────────────────────────────────────────────
# Modèle de marge — achat-revente
# ─────────────────────────────────────────────────────────────────────────────
# La marge calculée ici est une marge AVANT FISCALITÉ. Le régime applicable
# (plus-value des particuliers ou marchand de biens) est volontairement hors
# modèle : il se traite au cas par cas sur les annonces retenues.
#
# Chaque poste est neutralisable en mettant la variable à 0 dans Railway.

TRAVAUX_PAR_M2      = _flottant("TRAVAUX_PAR_M2", 1200)     # €/m²
FRAIS_NOTAIRE       = _flottant("FRAIS_NOTAIRE", 0.08)      # à l'acquisition

# Coût de portage sur la durée de l'opération : financement + charges courantes.
DUREE_PORTAGE_MOIS  = _flottant("DUREE_PORTAGE_MOIS", 12)
TAUX_FINANCEMENT    = _flottant("TAUX_FINANCEMENT", 0.045)  # 4,5 %/an
CHARGES_PORTAGE_M2  = _flottant("CHARGES_PORTAGE_M2", 45)   # €/m²/an : copro, TF, assurance

# Commission d'agence supportée à la revente.
FRAIS_AGENCE_REVENTE = _flottant("FRAIS_AGENCE_REVENTE", 0.03)

# ─────────────────────────────────────────────────────────────────────────────
# Zone — Butte Montmartre uniquement
# ─────────────────────────────────────────────────────────────────────────────
# prix_m2_ref     : prix de marché constaté, sert au calcul de décote
# prix_revente_m2 : prix atteignable après rénovation haut de gamme
ZONES = {
    "montmartre": {
        "libelle":         "Butte Montmartre",
        "cp":              ["75018"],
        "prix_m2_ref":     _flottant("PRIX_M2_REF", 10100),
        "prix_revente_m2": _flottant("PRIX_REVENTE_M2", 13000),
    }
}

# Surface minimale retenue : en dessous, les frais fixes mangent la marge.
SURFACE_MIN = _flottant("SURFACE_MIN", 25)

# Nombre d'annonces enrichies par cycle en visitant leur page. À baisser sur
# les runners GitHub, dont les plages d'IP sont surveillées par les portails.
ENRICH_MAX = int(os.getenv("ENRICH_MAX", "25"))

# Au-delà, on considère l'annonce comme morte.
MAX_JOURS = int(os.getenv("MAX_JOURS", "100"))
