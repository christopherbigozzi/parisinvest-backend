"""
authorize_gmail.py — à lancer UNE SEULE FOIS, en local, jamais sur Railway.

Ouvre le navigateur, demande l'autorisation sur le compte parisinvest18@gmail.com,
puis affiche le refresh token à recopier dans les variables Railway.

Usage :
    pip install google-auth-oauthlib
    python authorize_gmail.py chemin/vers/client_secret.json
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# gmail.modify : lecture des mails + pose du label « traité ».
# Pas de droit d'envoi, pas de suppression.
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    chemin = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(chemin, SCOPES)

    # access_type=offline + prompt=consent : sans ça, Google ne renvoie un
    # refresh token qu'à la toute première autorisation, et une seconde
    # exécution repart les mains vides.
    creds = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
        authorization_prompt_message="Ouvre cette adresse et connecte-toi "
                                     "avec parisinvest18@gmail.com :\n{url}",
        success_message="C'est bon, tu peux fermer cet onglet.",
    )

    with open(chemin) as f:
        secrets = json.load(f)
    bloc = secrets.get("installed") or secrets.get("web") or {}

    print("\n" + "=" * 62)
    print("À recopier dans Railway → Variables")
    print("=" * 62)
    print(f"GMAIL_CLIENT_ID={bloc.get('client_id', '')}")
    print(f"GMAIL_CLIENT_SECRET={bloc.get('client_secret', '')}")
    print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
    print(f"GMAIL_LABEL=parisinvest")
    print("=" * 62)

    if not creds.refresh_token:
        print("\nAucun refresh token renvoyé. Va sur "
              "https://myaccount.google.com/permissions, retire l'accès de "
              "l'application, puis relance ce script.")
    else:
        print("\nPense à publier l'application en Production dans l'écran de "
              "consentement OAuth : en statut Test, ce token expire sous 7 jours.")


if __name__ == "__main__":
    main()
