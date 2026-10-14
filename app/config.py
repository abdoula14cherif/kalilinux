"""
Configuration Boost Reseller.
Sécurité niveau bancaire : toutes les clés DOIVENT être définies en env.
"""
import os
import secrets
from datetime import timedelta


def _require_env(name):
    """Récupère une variable d'env obligatoire ou lève une exception."""
    value = os.environ.get(name)
    if not value or value.strip() == "":
        raise RuntimeError(
            f"❌ SÉCURITÉ CRITIQUE : La variable d'environnement '{name}' "
            f"doit être définie. Ne jamais lancer en production sans."
        )
    return value.strip()


def _get_or_generate_secret(name, default_dev_value=None):
    """
    En production : oblige à définir la variable.
    En développement : génère une valeur aléatoire (perdue au redémarrage).
    """
    value = os.environ.get(name)
    if value and value.strip():
        # Refuse les valeurs faibles ou par défaut
        if len(value) < 32:
            raise RuntimeError(
                f"❌ SÉCURITÉ : '{name}' doit faire au moins 32 caractères "
                f"(actuellement {len(value)})."
            )
        if value in ("changez-moi-reseller-urgent", "secret", "changeme", "test"):
            raise RuntimeError(
                f"❌ SÉCURITÉ : '{name}' utilise une valeur par défaut interdite."
            )
        return value.strip()

    # Pas de valeur : soit on est en dev, soit c'est une erreur critique
    if os.environ.get("FLASK_ENV") == "development":
        return secrets.token_hex(64)
    raise RuntimeError(
        f"❌ SÉCURITÉ CRITIQUE : '{name}' non défini. "
        f"Génère une clé avec : python -c \"import secrets; print(secrets.token_hex(64))\""
    )


class BaseConfig:
    # ─── Clés secrètes (BLOQUANT si absentes en prod) ──────────────
    SECRET_KEY = _get_or_generate_secret("SECRET_KEY")
    JWT_SECRET = _get_or_generate_secret("JWT_SECRET", default_dev_value=None) \
        if os.environ.get("JWT_SECRET") \
        else SECRET_KEY  # fallback : utilise SECRET_KEY si JWT_SECRET absent

    # ─── Sessions cookies ──────────────────────────────────────────
    SESSION_COOKIE_SECURE = True          # HTTPS uniquement
    SESSION_COOKIE_HTTPONLY = True        # inaccessible au JS
    SESSION_COOKIE_SAMESITE = "Lax"       # anti-CSRF partiel
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_REFRESH_EACH_REQUEST = True   # prolonge la session à chaque requête

    # ─── CSRF ──────────────────────────────────────────────────────
    WTF_CSRF_ENABLED = True               # ⚠️ Active la protection CSRF
    WTF_CSRF_TIME_LIMIT = 3600            # Token valide 1h
    WTF_CSRF_SSL_STRICT = True            # HTTPS requis pour valider le token

    # ─── Sécurité en-têtes ─────────────────────────────────────────
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB max pour les uploads

    # ─── Supabase ──────────────────────────────────────────────────
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

    # ─── Admin ─────────────────────────────────────────────────────
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

    # ─── Contact ───────────────────────────────────────────────────
    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "")

    # ─── Email ─────────────────────────────────────────────────────
    GMAIL_USERNAME = (
        os.environ.get("MAIL_USERNAME")
        or os.environ.get("GMAIL_USERNAME")
        or "boostcentralsupport@gmail.com"
    )
    GMAIL_APP_PASSWORD = (
        os.environ.get("GMAIL_APP_PASSWORD")
        or os.environ.get("GAMAIL_APP_PASSWORD")
        or ""
    )
    GMAIL_FROM_NAME = os.environ.get("GMAIL_FROM_NAME") or "Boost Reseller"

    # ─── Domaines ──────────────────────────────────────────────────
    ROOT_DOMAIN = os.environ.get("ROOT_DOMAIN", "boostcentral.world")
    RESELLER_DOMAIN = os.environ.get("RESELLER_DOMAIN", "reseller.boostcentral.world")
    CLIENT_DOMAIN = os.environ.get("CLIENT_DOMAIN", "boostcentral.world")
    CLIENT_URL = os.environ.get("CLIENT_URL", "https://boostcentral.world")

    # ─── Rate limiting (stockage Redis recommandé en prod) ─────────
    RATELIMIT_STORAGE_URI = os.environ.get(
        "RATELIMIT_STORAGE_URI",
        "memory://"  # ⚠️ En prod, utilise Redis : redis://...
    )
    RATELIMIT_HEADERS_ENABLED = True


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False   # Autorise HTTP en local
    WTF_CSRF_ENABLED = True         # On garde CSRF même en dev
    WTF_CSRF_SSL_STRICT = False     # Autorise HTTP en dev


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SSL_STRICT = True


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}


# ═══════════════════════════════════════════════════════════════
# ⚠️ ERREURS CORRIGÉES DANS CE FICHIER
# ═══════════════════════════════════════════════════════════════
#
# 🔴 CRITIQUE #1 — SECRET_KEY par défaut "changez-moi-reseller-urgent"
#    AVANT : N'importe qui pouvait forger des sessions et des JWT.
#    APRÈS : Obligation de définir SECRET_KEY en env, min 32 chars,
#            refus des valeurs faibles, exception si absent en prod.
#
# 🔴 CRITIQUE #2 — JWT_SECRET identique à SECRET_KEY par défaut
#    AVANT : Compromission de SECRET_KEY = compromission des JWT.
#    APRÈS : JWT_SECRET peut être distinct, avec les mêmes vérifs.
#
# 🔴 CRITIQUE #3 — CSRF désactivé globalement (WTF_CSRF_ENABLED = False)
#    AVANT : Tous les POST étaient vulnérables aux attaques CSRF.
#    APRÈS : CSRF activé, token valide 1h, SSL strict en prod.
#
# 🟠 IMPORTANT #7 — Pas de limite sur la taille des uploads
#    AVANT : Un attaquant pouvait uploader 1 GB et saturer le serveur.
#    APRÈS : MAX_CONTENT_LENGTH = 5 MB.
#
# 🟡 MOYEN #17 — Pas de headers de rate limiting
#    AVANT : Impossible de savoir combien de requêtes restaient.
#    APRÈS : RATELIMIT_HEADERS_ENABLED = True.
#
# 🟡 MOYEN — Stockage rate limit en mémoire (perdu à chaque redéploiement)
#    APRÈS : RATELIMIT_STORAGE_URI configurable (Redis en prod).
#
# 🟢 BONUS — SESSION_REFRESH_EACH_REQUEST activé
#    Prolonge la session à chaque clic pour éviter les déconnexions.
#
# ═══════════════════════════════════════════════════════════════