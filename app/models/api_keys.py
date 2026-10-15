"""
Gestion des clés API pour les revendeurs.
"""
import hashlib
import logging
import secrets
import requests
from datetime import datetime, timezone
from flask import current_app

logger = logging.getLogger(__name__)


def _headers(admin=True):
    key = current_app.config["SUPABASE_SERVICE_KEY"] if admin else current_app.config["SUPABASE_ANON_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _url(path):
    return current_app.config["SUPABASE_URL"] + "/rest/v1/" + path


def _hash_key(key):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def _generer_cle():
    """Genere une cle API au format bsk_live_xxxxx + prefixe + hash."""
    random_part = secrets.token_urlsafe(32)
    full_key = f"bsk_live_{random_part}"
    prefix = full_key[:16]
    return full_key, prefix, _hash_key(full_key)


def lister_cles(revendeur_id):
    """Liste toutes les cles API d'un revendeur."""
    try:
        r = requests.get(
            _url(f"api_keys?revendeur_id=eq.{revendeur_id}&order=created_at.desc"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"lister_cles: {type(e).__name__}")
        return []


def creer_cle(revendeur_id, nom, scopes):
    """Cree une nouvelle cle API. Retourne (dict, cle_complete) ou (None, None)."""
    if not nom or not isinstance(nom, str):
        return None, None
    if not scopes or not isinstance(scopes, list):
        scopes = ["boutique:read"]

    full_key, prefix, key_hash = _generer_cle()

    payload = {
        "revendeur_id": revendeur_id,
        "nom": nom[:60],
        "prefix": prefix,
        "key_hash": key_hash,
        "scopes": scopes,
        "actif": True,
    }

    try:
        r = requests.post(_url("api_keys"), json=payload, headers=_headers(), timeout=10)
        if r.status_code in (200, 201):
            result = r.json()
            if isinstance(result, list) and result:
                return result[0], full_key
        logger.error(f"creer_cle echec: {r.status_code}")
        return None, None
    except Exception as e:
        logger.error(f"creer_cle: {type(e).__name__}")
        return None, None


def revoquer_cle(cle_id, revendeur_id):
    """Revoque une cle API (soft delete)."""
    try:
        payload = {
            "actif": False,
            "revoked_at": datetime.now(timezone.utc).isoformat()
        }
        r = requests.patch(
            _url(f"api_keys?id=eq.{cle_id}&revendeur_id=eq.{revendeur_id}"),
            json=payload,
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"revoquer_cle: {type(e).__name__}")
        return False


def supprimer_cle(cle_id, revendeur_id):
    """Supprime definitivement une cle API."""
    try:
        r = requests.delete(
            _url(f"api_keys?id=eq.{cle_id}&revendeur_id=eq.{revendeur_id}"),
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_cle: {type(e).__name__}")
        return False


def verifier_cle(full_key):
    """Verifie une cle API et retourne l'enregistrement correspondant."""
    if not full_key or not full_key.startswith("bsk_live_"):
        return None
    key_hash = _hash_key(full_key)
    try:
        r = requests.get(
            _url(f"api_keys?key_hash=eq.{key_hash}&actif=eq.true&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        if isinstance(data, list) and data:
            cle = data[0]
            # Mise a jour derniere_utilisation
            try:
                requests.patch(
                    _url(f"api_keys?id=eq.{cle['id']}"),
                    json={"derniere_utilisation": datetime.now(timezone.utc).isoformat()},
                    headers=_headers(), timeout=5
                )
            except Exception:
                pass
            return cle
        return None
    except Exception as e:
        logger.error(f"verifier_cle: {type(e).__name__}")
        return None


def maj_derniere_utilisation(cle_id):
    """Met a jour le timestamp de derniere utilisation."""
    try:
        requests.patch(
            _url(f"api_keys?id=eq.{cle_id}"),
            json={"derniere_utilisation": datetime.now(timezone.utc).isoformat()},
            headers=_headers(), timeout=5
        )
    except Exception:
        pass


def cle_possede_scope(cle, scope_requis):
    """Verifie qu'une cle possede bien le scope demande."""
    if not cle:
        return False
    scopes = cle.get("scopes") or []
    if "all" in scopes:
        return True
    return scope_requis in scopes


def log_utilisation(cle_id, endpoint, methode, statut, ip=None):
    """Log une utilisation d'API (optionnel - a brancher plus tard)."""
    try:
        payload = {
            "api_key_id": cle_id,
            "endpoint": endpoint[:200],
            "method": methode,
            "status_code": statut,
            "ip": ip or "unknown",
        }
        requests.post(_url("api_logs"), json=payload, headers=_headers(), timeout=5)
    except Exception as e:
        logger.error(f"log_utilisation: {type(e).__name__}")