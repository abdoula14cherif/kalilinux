"""
Helpers de sécurité : sessions, JWT, décorateurs.
Sécurité niveau bancaire : anti-replay JTI, expiration stricte.
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
# 🔒 STOCKAGE ANTI-REPLAY DES JTI (in-memory pour Vercel)
# ═══════════════════════════════════════════════════════════════
# ⚠️ En production multi-instance (Vercel), ce dict est LOCAL à
#    chaque lambda. Pour une vraie protection anti-replay, migre
#    vers Redis ou une table Supabase (voir _marquer_jti_utilise).
_USED_JTIS = {}  # {jti: timestamp_expiration}


def _cleanup_expired_jtis():
    """Nettoie les JTI expirés pour éviter la fuite mémoire."""
    now = time.time()
    expired = [jti for jti, exp in _USED_JTIS.items() if exp < now]
    for jti in expired:
        _USED_JTIS.pop(jti, None)


def _jti_deja_utilise(jti):
    """Vérifie si un JTI a déjà été consommé."""
    _cleanup_expired_jtis()
    return jti in _USED_JTIS


def _marquer_jti_utilise(jti, expiration_ts):
    """Enregistre un JTI comme consommé jusqu'à son expiration."""
    _USED_JTIS[jti] = expiration_ts
    # Nettoyage opportuniste tous les ~100 enregistrements
    if len(_USED_JTIS) % 100 == 0:
        _cleanup_expired_jtis()


# ═══════════════════════════════════════════════════════════════
# 🔒 SESSIONS UTILISATEUR
# ═══════════════════════════════════════════════════════════════

def set_session(user_id, email, full_name=""):
    """Crée une session utilisateur sécurisée."""
    session.clear()  # Anti-fixation de session
    session.permanent = True
    session["user_id"] = user_id
    session["user_email"] = email
    session["user_name"] = full_name
    session["_csrf_ok"] = True  # Marqueur interne


def clear_session():
    """Détruit complètement la session."""
    session.clear()


def get_current_user():
    """Retourne les infos de l'utilisateur connecté (ou None)."""
    if "user_id" not in session:
        return None
    return {
        "id": session.get("user_id"),
        "email": session.get("user_email"),
        "full_name": session.get("user_name"),
    }


# ═══════════════════════════════════════════════════════════════
# 🔒 DÉCORATEUR login_required
# ═══════════════════════════════════════════════════════════════

def login_required(f):
    """Décorateur : oblige l'utilisateur à être connecté."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            # ⚠️ On stocke l'URL de retour SEULEMENT si elle est locale
            #    (évite l'open redirect via ?next=https://evil.com)
            next_url = request.url
            if next_url and next_url.startswith(request.host_url):
                session["next_url"] = next_url
            flash("Connectez-vous pour continuer.", "info")
            return redirect(url_for("auth.connexion"))
        return f(*args, **kwargs)
    return decorated_function


# ═══════════════════════════════════════════════════════════════
# 🔒 JWT SSO — Signature, expiration, anti-replay
# ═══════════════════════════════════════════════════════════════

def generer_token_sso(user_id, email, duree_minutes=5):
    """
    Génère un JWT signé pour le SSO.
    Expire par défaut en 5 minutes (courte durée = sécurité).
    """
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(minutes=duree_minutes)

    payload = {
        "user_id": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),  # Not Before
        "exp": int(expiration.timestamp()),
        "jti": secrets.token_hex(16),   # Anti-replay unique
        "iss": "boostcentral.world",     # Émetteur
        "aud": "reseller.boostcentral.world",  # Destinataire
    }

    secret = current_app.config.get("JWT_SECRET") or current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("JWT_SECRET manquant, impossible de signer.")

    return jwt.encode(payload, secret, algorithm="HS256")


def verifier_token_sso(token):
    """
    Vérifie un JWT SSO :
    - signature
    - expiration
    - émetteur / audience
    - anti-replay (JTI non réutilisé)
    Retourne le payload ou None si invalide.
    """
    try:
        secret = current_app.config.get("JWT_SECRET") or current_app.config.get("SECRET_KEY")
        if not secret:
            logger.error("JWT_SECRET manquant pour vérifier le token.")
            return None

        # ⚠️ On valide TOUT : signature, exp, nbf, iss, aud
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

        # ⚠️ Vérifie que le payload contient bien les champs attendus
        if not payload.get("user_id") or not payload.get("email"):
            logger.warning("JWT SSO : champs user_id ou email manquants.")
            return None

        # 🔒 ANTI-REPLAY : JTI déjà utilisé ?
        jti = payload["jti"]
        if _jti_deja_utilise(jti):
            logger.warning(f"JWT SSO rejoué (JTI déjà utilisé) : {jti}")
            return None

        # On marque ce JTI comme consommé
        _marquer_jti_utilise(jti, payload["exp"])

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("Token SSO expiré.")
        return None
    except jwt.InvalidTokenError as e:
        # ⚠️ Ne log QUE le type d'erreur, jamais le token (fuite possible)
        logger.warning(f"Token SSO invalide : {type(e).__name__}")
        return None
    except Exception as e:
        logger.exception(f"verifier_token_sso erreur inattendue : {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# 🔒 HELPERS SUPPLÉMENTAIRES
# ═══════════════════════════════════════════════════════════════

def token_expire_dans(token):
    """Retourne le nombre de secondes avant expiration (ou -1)."""
    try:
        secret = current_app.config.get("JWT_SECRET") or current_app.config.get("SECRET_KEY")
        payload = jwt.decode(token, secret, algorithms=["HS256"], options={"verify_signature": True, "verify_exp": False})
        return max(0, payload["exp"] - int(time.time()))
    except Exception:
        return -1


def _validate_next_url(url):
    """Valide qu'une URL de redirection est locale (anti open-redirect)."""
    if not url:
        return False
    # Autorise uniquement les chemins relatifs locaux
    if url.startswith("/") and not url.startswith("//"):
        return True
    # Autorise les URLs absolues de notre domaine uniquement
    if url.startswith(request.host_url):
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# ⚠️ ERREURS CORRIGÉES DANS CE FICHIER
# ═══════════════════════════════════════════════════════════════
#
# 🔴 CRITIQUE #13 — JTI généré mais JAMAIS vérifié (anti-replay absent)
#    AVANT : Un token SSO pouvait être rejoué pendant 5 minutes.
#    APRÈS : _USED_JTIS + _jti_deja_utilise + _marquer_jti_utilise.
#
# 🔴 CRITIQUE — Session fixation non bloquée
#    AVANT : Un attaquant pouvait fixer un session_id avant connexion.
#    APRÈS : session.clear() dans set_session().
#
# 🔴 CRITIQUE — Open redirect via ?next=
#    AVANT : next_url pouvait être https://evil.com → phishing.
#    APRÈS : Vérification que l'URL commence par request.host_url.
#
# 🟠 IMPORTANT — Champs JWT non obligatoires (require absent)
#    AVANT : Un token sans jti/iss/aud pouvait passer la validation.
#    APRÈS : options={"require": [...]} liste TOUS les champs obligatoires.
#
# 🟠 IMPORTANT — nbf (Not Before) non vérifié
#    AVANT : Un token futur pouvait être utilisé.
#    APRÈS : nbf généré et vérifié.
#
# 🟠 IMPORTANT — JWT sans iat/exp en timestamp (datetime = rejet)
#    AVANT : datetime.utcnow() (naïf) pouvait poser problème selon la lib.
#    APRÈS : int(now.timestamp()) en UTC timezone-aware.
#
# 🟡 MOYEN — Logs pouvaient contenir le token (fuite de credentials)
#    AVANT : logger.warning(f"Token invalide: {e}") pouvait log le token.
#    APRÈS : logger.warning(f"Token invalide : {type(e).__name__}").
#
# 🟡 MOYEN — Fuite mémoire : _USED_JTIS grossissait à l'infini
#    AVANT : Aucun nettoyage des JTI expirés.
#    APRÈS : _cleanup_expired_jtis() à chaque vérification.
#
# 🟢 BONUS — Fonction token_expire_dans() pour debug
#    Retourne le temps restant avant expiration.
#
# ⚠️ ATTENTION PROD : _USED_JTIS est LOCAL à chaque instance Vercel.
#    Pour une vraie protection multi-instance, migre vers Redis :
#    - redis.setex(f"jti:{jti}", ttl, "1")
#    - redis.exists(f"jti:{jti}")
#
# ═══════════════════════════════════════════════════════════════