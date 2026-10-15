"""
Helpers de securite : sessions, JWT, decorateurs.
SÉCURITÉ SÉVÈRE : sessions 24h max, JWT anti-replay, bannissement global.
"""
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import session, redirect, url_for, flash, current_app, request

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# ANTI-REPLAY DES JTI
# ═══════════════════════════════════════════════════════════════

_USED_JTIS = {}
SESSION_MAX_AGE = 24 * 3600  # 24 heures en secondes


def _cleanup_expired_jtis():
    now = time.time()
    expired = [jti for jti, exp in _USED_JTIS.items() if exp < now]
    for jti in expired:
        _USED_JTIS.pop(jti, None)


def _jti_deja_utilise(jti):
    _cleanup_expired_jtis()
    return jti in _USED_JTIS


def _marquer_jti_utilise(jti, expiration_ts):
    _USED_JTIS[jti] = expiration_ts
    if len(_USED_JTIS) % 100 == 0:
        _cleanup_expired_jtis()


# ═══════════════════════════════════════════════════════════════
# SESSIONS UTILISATEUR
# ═══════════════════════════════════════════════════════════════

def set_session(user_id, email, full_name=""):
    """Cree une session utilisateur securisee."""
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    session["user_email"] = email
    session["user_name"] = full_name
    session["login_at"] = time.time()
    session["last_activity"] = time.time()


def clear_session():
    """Detruit completement la session."""
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


def _session_valide():
    """Verifie que la session est encore valide (age + activite)."""
    if "user_id" not in session:
        return False

    login_at = session.get("login_at", 0)
    now = time.time()

    # Session expiree (24h)
    if now - login_at > SESSION_MAX_AGE:
        return False

    # Session inactive depuis plus de 8h
    last_activity = session.get("last_activity", login_at)
    if now - last_activity > 8 * 3600:
        return False

    return True


def _verifier_banni(user_id):
    """Verifie que l'utilisateur n'est pas banni."""
    try:
        from app.models.database import get_profile
        profile = get_profile(user_id)
        if profile and profile.get("banni"):
            return True
    except Exception as e:
        logger.error(f"_verifier_banni: {type(e).__name__}")
    return False


# ═══════════════════════════════════════════════════════════════
# DECORATEUR login_required
# ═══════════════════════════════════════════════════════════════

def login_required(f):
    """
    Decorateur : oblige l'utilisateur a etre connecte.
    SÉCURITÉ : verifie session valide + utilisateur non banni.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            next_url = request.url
            if next_url and next_url.startswith(request.host_url):
                session["next_url"] = next_url
            flash("Connectez-vous pour continuer.", "info")
            return redirect(url_for("auth.connexion"))

        # Verifie la duree de vie de la session
        if not _session_valide():
            clear_session()
            flash("Votre session a expire. Reconnectez-vous.", "warning")
            return redirect(url_for("auth.connexion"))

        # Verifie que l'utilisateur n'est pas banni (1 fois par minute max)
        last_check = session.get("_ban_check", 0)
        now = time.time()
        if now - last_check > 60:
            if _verifier_banni(session["user_id"]):
                clear_session()
                flash("Votre compte a ete suspendu. Contactez le support.", "error")
                return redirect(url_for("auth.connexion"))
            session["_ban_check"] = now

        # Met a jour l'activite
        session["last_activity"] = now

        return f(*args, **kwargs)
    return decorated_function


# ═══════════════════════════════════════════════════════════════
# JWT SSO
# ═══════════════════════════════════════════════════════════════

def generer_token_sso(user_id, email, duree_minutes=5):
    """Genere un JWT signe pour le SSO."""
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(minutes=duree_minutes)

    payload = {
        "user_id": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expiration.timestamp()),
        "jti": secrets.token_hex(16),
        "iss": "boostcentral.world",
        "aud": "reseller.boostcentral.world",
    }

    secret = current_app.config.get("JWT_SECRET") or current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET manquant.")

    return jwt.encode(payload, secret, algorithm="HS256")


def verifier_token_sso(token):
    """Verifie un JWT SSO avec anti-replay."""
    try:
        secret = current_app.config.get("JWT_SECRET") or current_app.config.get("SECRET_KEY")
        if not secret:
            logger.error("JWT_SECRET manquant.")
            return None

        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="reseller.boostcentral.world",
            issuer="boostcentral.world",
            options={
                "require": ["exp", "iat", "nbf", "jti", "iss", "aud", "user_id", "email"],
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )

        if not payload.get("user_id") or not payload.get("email"):
            logger.warning("JWT SSO : champs manquants.")
            return None

        jti = payload["jti"]
        if _jti_deja_utilise(jti):
            logger.warning(f"JWT SSO rejoue : {jti}")
            return None

        _marquer_jti_utilise(jti, payload["exp"])
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Token SSO expire.")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Token SSO invalide : {type(e).__name__}")
        return None
    except Exception as e:
        logger.exception(f"verifier_token_sso : {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# VALIDATION URL
# ═══════════════════════════════════════════════════════════════

def valider_url(url, domaines_autorises=None):
    """Valide une URL pour eviter les injections javascript:, data:, etc."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url:
        return None
    if len(url) > 500:
        return None
    url_lower = url.lower()
    if not url_lower.startswith(("http://", "https://")):
        return None
    interdits = ("javascript:", "data:", "vbscript:", "file:", "about:")
    for interdit in interdits:
        if interdit in url_lower:
            return None
    if domaines_autorises:
        from urllib.parse import urlparse
        try:
            host = urlparse(url).hostname or ""
            host = host.lower()
            if not any(host == d or host.endswith("." + d) for d in domaines_autorises):
                return None
        except Exception:
            return None
    return url


def valider_url_reseau_social(url):
    """Valide une URL de reseau social."""
    domaines = (
        "facebook.com", "fb.com", "instagram.com", "tiktok.com",
        "twitter.com", "x.com", "youtube.com", "youtu.be",
        "telegram.org", "t.me", "wa.me", "whatsapp.com",
        "linkedin.com", "pinterest.com", "snapchat.com",
        "spotify.com", "soundcloud.com", "twitch.tv", "discord.com",
        "threads.net", "deezer.com",
    )
    return valider_url(url, domaines_autorises=domaines)


def valider_url_generique(url):
    """Valide une URL generique."""
    return valider_url(url)