"""
Gestion des applications OAuth 2.0 pour les revendeurs.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timezone
import requests
from flask import current_app

logger = logging.getLogger(__name__)

SCOPES_DISPONIBLES = [
    "boutique:read", "boutique:write",
    "produits:read", "produits:write",
    "commandes:read", "commandes:write",
    "clients:read",
    "stats:read",
]


def _headers():
    key = current_app.config["SUPABASE_SERVICE_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _url(path):
    return current_app.config["SUPABASE_URL"] + "/rest/v1/" + path


def _hash_secret(secret):
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _generer_client_id():
    return "bsk_client_" + secrets.token_hex(16)


def _generer_client_secret():
    return "bsk_secret_" + secrets.token_urlsafe(48)


def lister_apps(revendeur_id):
    try:
        r = requests.get(
            _url(f"oauth_apps?revendeur_id=eq.{revendeur_id}&order=created_at.desc"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        if not isinstance(data, list):
            return []
        for app in data:
            app.pop("client_secret_hash", None)
        return data
    except Exception as e:
        logger.error(f"lister_apps: {type(e).__name__}")
        return []


def creer_app(revendeur_id, nom, description, redirect_uris, scopes):
    if not nom or not redirect_uris:
        return None, None, None

    client_id = _generer_client_id()
    client_secret = _generer_client_secret()

    payload = {
        "revendeur_id": revendeur_id,
        "nom": nom[:80],
        "description": (description or "")[:500] or None,
        "client_id": client_id,
        "client_secret_hash": _hash_secret(client_secret),
        "redirect_uris": redirect_uris,
        "scopes": scopes or [],
        "actif": True,
    }

    try:
        r = requests.post(_url("oauth_apps"), json=payload, headers=_headers(), timeout=10)
        if r.status_code in (200, 201):
            result = r.json()
            if isinstance(result, list) and result:
                app = result[0]
                app.pop("client_secret_hash", None)
                return app, client_id, client_secret
        logger.error(f"creer_app: {r.status_code}")
        return None, None, None
    except Exception as e:
        logger.error(f"creer_app: {type(e).__name__}")
        return None, None, None


def supprimer_app(app_id, revendeur_id):
    try:
        r = requests.delete(
            _url(f"oauth_apps?id=eq.{app_id}&revendeur_id=eq.{revendeur_id}"),
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_app: {type(e).__name__}")
        return False


def toggle_app(app_id, revendeur_id, actif):
    try:
        r = requests.patch(
            _url(f"oauth_apps?id=eq.{app_id}&revendeur_id=eq.{revendeur_id}"),
            json={"actif": actif}, headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_app: {type(e).__name__}")
        return False


def regenerer_secret(app_id, revendeur_id):
    """Genere un nouveau client_secret."""
    try:
        # Verifier que l'app appartient au revendeur
        r = requests.get(
            _url(f"oauth_apps?id=eq.{app_id}&revendeur_id=eq.{revendeur_id}&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        if not isinstance(data, list) or not data:
            return None

        nouveau_secret = _generer_client_secret()

        r2 = requests.patch(
            _url(f"oauth_apps?id=eq.{app_id}"),
            json={"client_secret_hash": _hash_secret(nouveau_secret)},
            headers=_headers(), timeout=10
        )
        if r2.status_code < 300:
            return nouveau_secret
        return None
    except Exception as e:
        logger.error(f"regenerer_secret: {type(e).__name__}")
        return None


def lister_logs(app_id, limit=50):
    try:
        r = requests.get(
            _url(f"oauth_logs?app_id=eq.{app_id}&order=created_at.desc&limit={limit}"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"lister_logs: {type(e).__name__}")
        return []


def log_oauth_event(app_id, event, ip=None, user_agent=None):
    try:
        requests.post(
            _url("oauth_logs"),
            json={
                "app_id": app_id,
                "event": event[:100],
                "ip": ip,
                "user_agent": (user_agent or "")[:200],
            },
            headers=_headers(), timeout=5
        )
    except Exception as e:
        logger.error(f"log_oauth_event: {type(e).__name__}")