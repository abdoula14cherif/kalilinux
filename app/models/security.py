"""
Helpers de securite : sessions, JWT, decorateurs, anti-bot.
SÉCURITÉ SÉVÈRE : sessions, bannissement, detection bots, honeypot.
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
# ANTI-REPLAY JTI + SESSION
# ═══════════════════════════════════════════════════════════════

_USED_JTIS = {}
SESSION_MAX_AGE = 24 * 3600  # 24h
SESSION_INACTIVITY = 8 * 3600  # 8h d'inactivite max


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
# DETECTION DE BOTS
# ═══════════════════════════════════════════════════════════════

_BOTS_CONNUS = (
    "curl", "wget", "python-requests", "python-urllib", "scrapy",
    "httrack", "ahrefs", "semrushbot", "mj12bot", "dotbot",
    "petalbot", "bytespider", "gptbot", "chatgpt", "claudebot",
    "googlebot-news", "yandexbot", "baiduspider", "sogou",
    "exabot", "facebot", "ia_archiver", "netcraft", "zgrab",
    "masscan", "nmap", "sqlmap", "nikto", "acunetix", "nessus",
    "openvas", "havij", "whatweb", "dirbuster", "gobuster",
    "wfuzz", "hydra", "medusa", "patator",
)

_UA_AUTORISES = (
    "boostreseller-python/",
    "boostreseller-js/",
)


def est_bot():
    """
    Detecte les bots/scrapers/scanners basiques (via User-Agent).
    Retourne True si l'utilisateur semble etre un bot.
    """
    ua = (request.headers.get("User-Agent") or "").lower().strip()

    if not ua:
        return True

    if any(a in ua for a in _UA_AUTORISES):
        return False

    if any(bot in ua for bot in _BOTS_CONNUS):
        return True

    if len(ua) < 15:
        return True

    return False


def est_bot_fort():
    """
    Detection renforcee : combine User-Agent + headers suspects.
    Plus stricte que est_bot().
    """
    if est_bot():
        return True

    # Pas d'Accept-Language (navigateur reel en envoie toujours)
    if not request.headers.get("Accept-Language"):
        return True

    # Pas d'Accept
    if not request.headers.get("Accept"):
        return True

    return False


def _log_bot(endpoint):
    """Log une tentative de bot."""
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "")).split(",")[0].strip()
    ua = (request.headers.get("User-Agent") or "")[:120]
    logger.warning(f"[BOT DETECTE] endpoint={endpoint} | IP={ip} | UA={ua}")


# ═══════════════════════════════════════════════════════════════
# HONEYPOT
# ═══════════════════════════════════════════════════════════════

def verifier_honeypot():
    """
    Verifie que le champ cache 'website' n'a pas ete rempli.
    Si rempli → c'est un bot.
    Retourne True si OK (pas de bot), False si bot.
    """
    honeypot = request.form.get("website", "").strip()
    return not honeypot


# ═══════════════════════════════════════════════════════════════
# SESSIONS UTILISATEUR
# ═══════════════════════════════════════════════════════════════

def set_session(user_id, email, full_name=""):
    """Cree une session securisee."""
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    session["user_email"] = email
    session["user_name"] = full_name
    session["login_at"] = time.time()
    session["last_activity"] = time.time()
    session["_fp"] = _empreinte_client()


def clear_session():
    session.clear()


def get_current_user():
    if "user_id" not in session:
        return None
    return {
        "id": session.get("user_id"),
        "email": session.get("user_email"),
        "full_name": session.get("user_name"),
    }


def _empreinte_client():
    """Genere une empreinte du client pour detecter le vol de session."""
    ua = request.headers.get("User-Agent", "")
    lang = request.headers.get("Accept-Language", "")
    return f"{ua[:50]}|{lang[:30]}"


def _session_valide():
    """Verifie session + empreinte."""
    if "user_id" not in session:
        return False

    login_at = session.get("login_at", 0)
    now = time.time()

    # Duree absolue
    if now - login_at > SESSION_MAX_AGE:
        return False

    # Inactivite
    last_activity = session.get("last_activity", login_at)
    if now - last_activity > SESSION_INACTIVITY:
        return False

    # Empreinte client
    fp_actuelle = _empreinte_client()
    if session.get("_fp") and session["_fp"] != fp_actuelle:
        logger.warning(f"[SECURITE] Empreinte client modifiee pour {session.get('user_email')}")
        return False

    return True


def _verifier_banni(user_id):
    try:
        from app.models.database import get_profile
        profile = get_profile(user_id)
        if profile and profile.get("banni"):
            return True
    except Exception as e:
        logger.error(f"_verifier_banni: {type(e).__name__}")
    return False


# ═══════════════════════════════════════════════════════════════
# DECORATEURS
# ═══════════════════════════════════════════════════════════════

def login_required(f):
    """Decorateur : oblige l'utilisateur a etre connecte."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            next_url = request.url
            if next_url and next_url.startswith(request.host_url):
                session["next_url"] = next_url
            flash("Connectez-vous pour continuer.", "info")
            return redirect(url_for("auth.connexion"))

        if not _session_valide():
            clear_session()
            flash("Votre session a expire. Reconnectez-vous.", "warning")
            return redirect(url_for("auth.connexion"))

        last_check = session.get("_ban_check", 0)
        now = time.time()
        if now - last_check > 60:
            if _verifier_banni(session["user_id"]):
                clear_session()
                flash("Votre compte a ete suspendu. Contactez le support.", "error")
                return redirect(url_for("auth.connexion"))
            session["_ban_check"] = now

        session["last_activity"] = now
        return f(*args, **kwargs)
    return decorated_function


def bot_blocked(f):
    """
    Decorateur : bloque les bots/scrapers.
    A utiliser sur les routes publiques sensibles.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if est_bot_fort():
            _log_bot(request.path)
            return "Forbidden", 403
        return f(*args, **kwargs)
    return decorated_function


# ═══════════════════════════════════════════════════════════════
# JWT SSO (garde pour compatibilite)
# ═══════════════════════════════════════════════════════════════

def generer_token_sso(user_id, email, duree_minutes=5):
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
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not url or len(url) > 500:
        return None
    if not url.lower().startswith(("http://", "https://")):
        return None
    interdits = ("javascript:", "data:", "vbscript:", "file:", "about:")
    if any(i in url.lower() for i in interdits):
        return None
    if domaines_autorises:
        from urllib.parse import urlparse
        try:
            host = (urlparse(url).hostname or "").lower()
            if not any(host == d or host.endswith("." + d) for d in domaines_autorises):
                return None
        except Exception:
            return None
    return url


def valider_url_reseau_social(url):
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
    return valider_url(url)