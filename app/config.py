"""
Configuration Boost Central.
Optimisé pour Vercel & Serverless.
"""
import os
from datetime import timedelta


class BaseConfig:
    # ─── SECRET_KEY ──────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "boostcentral-fallback-2026-change-me-later")

    # ─── CSRF ────────────────────────────────────────────────
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = False 

    # ─── SESSIONS (LE FIX EST ICI) ───────────────────────────
    # Indispensable pour que Vercel garde la session entre 2 requêtes
    SESSION_TYPE = "cookie"              
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # Cookie settings
    SESSION_COOKIE_NAME = "boost_session"
    SESSION_COOKIE_SECURE = True       # HTTPS obligatoire
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"    # Lax est plus compatible que None sur mobile
    SESSION_REFRESH_EACH_REQUEST = True

    # ─── Limite upload ────────────────────────────────────────
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # ─── Supabase ─────────────────────────────────────────────
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

    # ─── Admin & Contact ──────────────────────────────────────
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "abdoula13cherif@gmail.com")
    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "237658033690")

    # ─── Paiements & API ──────────────────────────────────────
    SOINA_PAY_URL = os.environ.get("SOINA_PAY_URL", "https://soinapay.com/pay/zmnmqbap")
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
    BOOSTCI_API_KEY = os.environ.get("BOOSTCI_API_KEY", "")
    BOOSTCI_API_URL = os.environ.get("BOOSTCI_API_URL", "https://boostci.com/api/v2")

    # ─── Autres ───────────────────────────────────────────────
    ORDERS_PER_PAGE = 20
    RECHARGES_PER_PAGE = 10
    USD_RATE = 600.0
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}