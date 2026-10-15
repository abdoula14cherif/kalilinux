"""
Gestion des codes SSO temporaires.
SÉCURITÉ : code usage unique, expire en 2 minutes, anti-replay.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
import requests
from flask import current_app

logger = logging.getLogger(__name__)


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


def creer_code_sso(user_id, email, full_name=None, duree_secondes=120):
    """
    Cree un code SSO unique et temporaire.
    SÉCURITÉ :
    - Code aleatoire de 40 caracteres
    - Usage unique
    - Expire en 2 minutes par defaut
    """
    if not user_id or not email:
        logger.error("creer_code_sso: user_id ou email manquant")
        return None

    # Genere un code aleatoire sur
    code = secrets.token_urlsafe(32)[:40]
    expires = datetime.now(timezone.utc) + timedelta(seconds=duree_secondes)

    payload = {
        "code": code,
        "user_id": user_id,
        "email": email,
        "full_name": full_name,
        "expires_at": expires.isoformat(),
    }

    try:
        r = requests.post(_url("sso_tokens"), json=payload, headers=_headers(), timeout=10)
        if r.status_code in (200, 201):
            logger.info(f"Code SSO cree pour {email}")
            return code
        logger.error(f"creer_code_sso: {r.status_code} - {r.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"creer_code_sso: {type(e).__name__}")
        return None


def utiliser_code_sso(code):
    """
    Verifie et consomme un code SSO.
    SÉCURITÉ :
    - Verifie l'existence du code
    - Verifie qu'il n'a pas ete utilise
    - Verifie qu'il n'a pas expire
    - Le marque comme utilise (anti-replay)
    
    Retourne {user_id, email, full_name} ou None.
    """
    if not code or not isinstance(code, str) or len(code) < 20:
        return None

    try:
        # Cherche le code
        r = requests.get(
            _url(f"sso_tokens?code=eq.{code}&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        if not isinstance(data, list) or not data:
            logger.warning("Code SSO introuvable")
            return None

        token = data[0]

        # Deja utilise ?
        if token.get("utilise"):
            logger.warning(f"Code SSO deja utilise (email={token.get('email')})")
            return None

        # Expire ?
        expires_at = token.get("expires_at", "")
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) > exp:
                logger.warning(f"Code SSO expire (email={token.get('email')})")
                return None
        except Exception as e:
            logger.error(f"Parse expires_at : {type(e).__name__}")
            return None

        # Marquer comme utilise IMMEDIATEMENT (anti-replay)
        patch_r = requests.patch(
            _url(f"sso_tokens?id=eq.{token['id']}"),
            json={
                "utilise": True,
                "utilise_le": datetime.now(timezone.utc).isoformat()
            },
            headers=_headers(), timeout=10
        )
        
        if patch_r.status_code >= 300:
            logger.error(f"Impossible de marquer le code comme utilise")
            return None

        logger.info(f"Code SSO consomme pour {token.get('email')}")
        return {
            "user_id": token.get("user_id"),
            "email": token.get("email"),
            "full_name": token.get("full_name"),
        }
    except Exception as e:
        logger.error(f"utiliser_code_sso: {type(e).__name__}")
        return None


def nettoyer_codes_expires():
    """Nettoie les codes expires (a appeler periodiquement)."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        requests.delete(
            _url(f"sso_tokens?expires_at=lt.{cutoff}"),
            headers=_headers(), timeout=10
        )
    except Exception as e:
        logger.error(f"nettoyer_codes_expires: {type(e).__name__}")