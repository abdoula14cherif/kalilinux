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
    WTF_CSRF_SSL_STRICT = False # Doit être False derrière un proxy (Vercel)

    # ─── Sessions ─────────────────────────────────────────────
    # ⚠️ C'est ICI que se joue la connexion en production
    SESSION_COOKIE_SECURE = True     # Obligatoire en HTTPS (Vercel)
    SESSION_COOKIE_HTTPONLY = True   # Sécurité
    SESSION_COOKIE_SAMESITE = "Lax"  # "Lax" est obligatoire pour que le POST de login fonctionne
    PERMANENT_SESSION_LIFETIME = timedelta(days=7) # La session dure 7 jours
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
    # En local (HTTP), on enlève le Secure sinon ça bloque
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    # En prod (HTTPS), on garde le Secure
    SESSION_COOKIE_SECURE = True


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": ProductionConfig,
}