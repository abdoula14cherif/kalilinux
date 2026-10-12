import os
from datetime import timedelta


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "changez-moi-reseller")
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # Supabase (partagee avec le site Boost Central)
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

    # Admin
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "abdoula13cherif@gmail.com")

    # Contact
    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "237658033690")

    # Email
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

    # Domaines
    ROOT_DOMAIN = os.environ.get("ROOT_DOMAIN", "boostcentral.world")
    RESELLER_DOMAIN = os.environ.get("RESELLER_DOMAIN", "reseller.boostcentral.world")
    CLIENT_DOMAIN = os.environ.get("CLIENT_DOMAIN", "boostcentral.world")

    # JWT SSO (partage avec boostcentral)
    JWT_SECRET = os.environ.get("JWT_SECRET", SECRET_KEY)


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}