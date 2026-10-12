"""
Helpers de securite : sessions, JWT, decorateurs.
"""
import logging
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import session, redirect, url_for, flash, current_app, request

logger = logging.getLogger(__name__)


def set_session(user_id, email, full_name=""):
    """Cree une session utilisateur."""
    session.permanent = True
    session["user_id"] = user_id
    session["user_email"] = email
    session["user_name"] = full_name


def clear_session():
    """Detruit la session."""
    session.clear()


def get_current_user():
    """Retourne les infos de l'utilisateur connecte (ou None)."""
    if "user_id" not in session:
        return None
    return {
        "id": session.get("user_id"),
        "email": session.get("user_email"),
        "full_name": session.get("user_name"),
    }


def login_required(f):
    """Decorateur : oblige l'utilisateur a etre connecte."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            session["next_url"] = request.url
            flash("Connectez-vous pour continuer.", "info")
            return redirect(url_for("auth.connexion"))
        return f(*args, **kwargs)
    return decorated_function


def generer_token_sso(user_id, email, duree_minutes=5):
    """
    Genere un JWT signe pour le SSO.
    Expire par defaut en 5 minutes.
    """
    import secrets
    now = datetime.utcnow()
    payload = {
        "user_id": user_id,
        "email": email,
        "iat": now,
        "exp": now + timedelta(minutes=duree_minutes),
        "jti": secrets.token_hex(16),  # Anti-replay
        "iss": "boostcentral.world",
        "aud": "reseller.boostcentral.world",
    }
    secret = current_app.config.get("JWT_SECRET") or current_app.config.get("SECRET_KEY")
    token = jwt.encode(payload, secret, algorithm="HS256")
    return token


def verifier_token_sso(token):
    """
    Verifie un JWT SSO et retourne le payload, ou None si invalide/expire.
    """
    try:
        secret = current_app.config.get("JWT_SECRET") or current_app.config.get("SECRET_KEY")
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="reseller.boostcentral.world",
            issuer="boostcentral.world"
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token SSO expire")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token SSO invalide: {e}")
        return None
    except Exception as e:
        logger.error(f"verifier_token_sso: {e}")
        return None