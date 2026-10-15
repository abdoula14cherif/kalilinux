"""
Gestion des webhooks personnalisés pour les revendeurs.
Envoie des notifications HTTP POST signées HMAC.
"""
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
import requests
from flask import current_app

logger = logging.getLogger(__name__)

# Evenements supportes
EVENTS_DISPONIBLES = [
    "commande.creee",
    "commande.confirmee",
    "commande.en_livraison",
    "commande.livree",
    "commande.annulee",
    "paiement.recu",
    "client.inscrit",
    "avis.ajoute",
    "produit.stock_bas",
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


# ═══════════════════════════════════════════════════════════════
# CRUD
# ═══════════════════════════════════════════════════════════════

def lister_webhooks(revendeur_id):
    try:
        r = requests.get(
            _url(f"webhooks?revendeur_id=eq.{revendeur_id}&order=created_at.desc"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"lister_webhooks: {type(e).__name__}")
        return []


def get_webhook(webhook_id, revendeur_id):
    try:
        r = requests.get(
            _url(f"webhooks?id=eq.{webhook_id}&revendeur_id=eq.{revendeur_id}&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_webhook: {type(e).__name__}")
        return None


def creer_webhook(revendeur_id, url_endpoint, events, actif=True):
    if not url_endpoint or not url_endpoint.startswith(("http://", "https://")):
        return None, None

    secret = "whsec_" + secrets.token_hex(32)

    payload = {
        "revendeur_id": revendeur_id,
        "url": url_endpoint[:500],
        "secret": secret,
        "events": events or [],
        "actif": actif,
    }

    try:
        r = requests.post(_url("webhooks"), json=payload, headers=_headers(), timeout=10)
        if r.status_code in (200, 201):
            result = r.json()
            if isinstance(result, list) and result:
                return result[0], secret
        logger.error(f"creer_webhook: {r.status_code}")
        return None, None
    except Exception as e:
        logger.error(f"creer_webhook: {type(e).__name__}")
        return None, None


def maj_webhook(webhook_id, revendeur_id, data):
    try:
        r = requests.patch(
            _url(f"webhooks?id=eq.{webhook_id}&revendeur_id=eq.{revendeur_id}"),
            json=data, headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"maj_webhook: {type(e).__name__}")
        return False


def supprimer_webhook(webhook_id, revendeur_id):
    try:
        r = requests.delete(
            _url(f"webhooks?id=eq.{webhook_id}&revendeur_id=eq.{revendeur_id}"),
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_webhook: {type(e).__name__}")
        return False


def lister_logs(webhook_id, limit=50):
    try:
        r = requests.get(
            _url(f"webhook_logs?webhook_id=eq.{webhook_id}&order=created_at.desc&limit={limit}"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"lister_logs: {type(e).__name__}")
        return []


# ═══════════════════════════════════════════════════════════════
# ENVOI
# ═══════════════════════════════════════════════════════════════

def _signer(secret, timestamp, payload_json):
    message = f"{timestamp}.{payload_json}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def envoyer_webhook(webhook, event, data):
    try:
        timestamp = int(time.time())
        payload = {"event": event, "timestamp": timestamp, "data": data}
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        signature = _signer(webhook["secret"], timestamp, payload_json)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "BoostReseller-Webhook/1.0",
            "X-Boost-Event": event,
            "X-Boost-Signature": f"t={timestamp},v1={signature}",
            "X-Boost-Delivery": secrets.token_hex(16),
        }

        start = time.time()
        try:
            r = requests.post(
                webhook["url"],
                data=payload_json.encode("utf-8"),
                headers=headers,
                timeout=10
            )
            duration = int((time.time() - start) * 1000)
            succes = 200 <= r.status_code < 300
            return succes, r.status_code, duration, r.text[:500]
        except requests.Timeout:
            return False, 0, int((time.time() - start) * 1000), "Timeout"
        except Exception as e:
            return False, 0, int((time.time() - start) * 1000), str(e)[:500]
    except Exception as e:
        logger.error(f"envoyer_webhook: {type(e).__name__}")
        return False, 0, 0, str(e)[:500]


def log_envoi(webhook_id, event, payload, status, body, duration, succes):
    try:
        requests.post(
            _url("webhook_logs"),
            json={
                "webhook_id": webhook_id,
                "event": event,
                "payload": payload,
                "response_status": status,
                "response_body": body[:500] if body else None,
                "duration_ms": duration,
                "succes": succes,
            },
            headers=_headers(), timeout=5
        )
    except Exception as e:
        logger.error(f"log_envoi: {type(e).__name__}")


def maj_stats(webhook_id, succes):
    try:
        w = requests.get(
            _url(f"webhooks?id=eq.{webhook_id}&limit=1"),
            headers=_headers(), timeout=5
        ).json()
        if not w:
            return
        w = w[0]
        requests.patch(
            _url(f"webhooks?id=eq.{webhook_id}"),
            json={
                "derniere_utilisation": datetime.now(timezone.utc).isoformat(),
                "total_envois": (w.get("total_envois") or 0) + 1,
                "total_succes": (w.get("total_succes") or 0) + (1 if succes else 0),
                "total_echecs": (w.get("total_echecs") or 0) + (0 if succes else 1),
            },
            headers=_headers(), timeout=5
        )
    except Exception as e:
        logger.error(f"maj_stats: {type(e).__name__}")


def declencher_event(revendeur_id, event, data):
    """Declenche un event vers tous les webhooks actifs du revendeur."""
    if event not in EVENTS_DISPONIBLES:
        return
    try:
        for wh in lister_webhooks(revendeur_id):
            if not wh.get("actif"):
                continue
            events_ecoutes = wh.get("events") or []
            if event not in events_ecoutes:
                continue
            succes, status, duration, body = envoyer_webhook(wh, event, data)
            log_envoi(wh["id"], event, data, status, body, duration, succes)
            maj_stats(wh["id"], succes)
    except Exception as e:
        logger.error(f"declencher_event: {type(e).__name__}")


def tester_webhook(webhook_id, revendeur_id):
    """Envoie un payload de test."""
    wh = get_webhook(webhook_id, revendeur_id)
    if not wh:
        return False, "Webhook introuvable"
    test_data = {
        "test": True,
        "message": "Ceci est un evenement de test",
        "date": datetime.now(timezone.utc).isoformat(),
    }
    succes, status, duration, body = envoyer_webhook(wh, "test", test_data)
    log_envoi(wh["id"], "test", test_data, status, body, duration, succes)
    maj_stats(wh["id"], succes)
    if succes:
        return True, f"Succes ! HTTP {status} en {duration}ms"
    return False, f"Echec : HTTP {status} - {body[:100]}"