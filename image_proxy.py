"""
Proxy d'images — sert les images externes sans problème CORS.
Lance un serveur HTTP simple sur le port 8080.
Railway expose ce port automatiquement.
"""
import os
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

PORT = int(os.getenv("IMAGE_PROXY_PORT", "8080"))

HEADERS_PROXY = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
}


class ImageProxyHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            # Extraire l'URL cible depuis ?url=...
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            target_url = params.get("url", [None])[0]

            if not target_url:
                self.send_error(400, "Missing url parameter")
                return

            # Valider que c'est bien une image immo
            allowed = [
                "pictures.notif.immo",
                "img.leboncoin.fr",
                "storage.googleapis.com",
                "img.gensdeconfiance.com",
                "www.century21.fr",
                "photos.seloger.com",
                "bienici.com",
                "notif.immo",
                "amazonaws.com",
            ]
            domain = urlparse(target_url).netloc
            if not any(a in domain for a in allowed):
                self.send_error(403, "Domain not allowed")
                return

            # Récupérer l'image
            resp = requests.get(
                target_url,
                headers=HEADERS_PROXY,
                timeout=8,
                stream=True
            )

            if resp.status_code != 200:
                self.send_error(404, "Image not found")
                return

            # Servir l'image avec headers CORS
            content_type = resp.headers.get("Content-Type", "image/jpeg")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(resp.content)

        except Exception as e:
            try:
                self.send_error(500, str(e))
            except Exception:
                pass

    def log_message(self, format, *args):
        pass  # Silencer les logs HTTP


def start_proxy():
    server = HTTPServer(("0.0.0.0", PORT), ImageProxyHandler)
    print(f"  [Proxy] Image proxy démarré sur port {PORT}")
    server.serve_forever()


def start_proxy_thread():
    """Lance le proxy dans un thread séparé pour ne pas bloquer main.py."""
    t = threading.Thread(target=start_proxy, daemon=True)
    t.start()
