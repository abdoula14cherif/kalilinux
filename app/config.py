"""
Configuration Boost Central.
Version securisee pour Production (Vercel).
"""
import os
from datetime import timedelta


class BaseConfig:
    # ─── SECRET_KEY ──────────────────────────────────────────
    SECRET_KEY = os.environ.get("SECRET_KEY", "boostcentral-fallback-2026-change-me-later")

    # ─── CSRF (Actif) ────────────────────────────────────────
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = False 

    # ─── Sessions (Optimisé Vercel/HTTPS) ────────────────────
    SESSION_COOKIE_SECURE = True     
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "None"  # 👈 LE FIX EST ICI
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_REFRESH_EACH_REQUEST = True

    # ─── Limite upload ────────────────────────────────────────
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 Mo

    # ─── Supabase ─────────────────────────────────────────────
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

    # ─── Admin ────────────────────────────────────────────────
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "abdoula13cherif@gmail.com")

    # ─── Contact ──────────────────────────────────────────────
    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "237658033690")

    # ─── Paiements ────────────────────────────────────────────
    SOINA_PAY_URL = os.environ.get("SOINA_PAY_URL", "https://soinapay.com/pay/zmnmqbap")

    # ─── Email ────────────────────────────────────────────────
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

    # ─── Fournisseur BOOSTCI ──────────────────────────────────
    BOOSTCI_API_KEY = os.environ.get("BOOSTCI_API_KEY", "")
    BOOSTCI_API_URL = os.environ.get("BOOSTCI_API_URL", "https://boostci.com/api/v2")

    # ─── Pagination ───────────────────────────────────────────
    ORDERS_PER_PAGE = 20
    RECHARGES_PER_PAGE = 10

    # ─── Taux ─────────────────────────────────────────────────
    USD_RATE = 600.0

    # ─── Rate limiting ────────────────────────────────────────
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    # En local (HTTP), on enlève le Secure et on remet Lax pour que ça marche
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = "Lax"


class ProductionConfig(BaseConfig):
    DEBUG = False
    # En prod (HTTPS), on garde le Secure et None
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "None"


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}