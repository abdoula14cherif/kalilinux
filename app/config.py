import os
from datetime import timedelta


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "changez-moi-reseller-urgent")
    JWT_SECRET = os.environ.get("SECRET_KEY", SECRET_KEY)

    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

    # Supabase (partagee avec boostcentral)
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

    # Admin
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "abdoula13cherif@gmail.com")

    # Contact
    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "237658033690")

    # Email Boost Reseller (compte dedie, separe de Boost Central)
    GMAIL_USERNAME = os.environ.get("GMAIL_USERNAME", "boostcentralsupport@gmail.com")
    GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
    GMAIL_FROM_NAME = os.environ.get("GMAIL_FROM_NAME", "Boost Reseller")

    # Domaines
    ROOT_DOMAIN = os.environ.get("ROOT_DOMAIN", "boostcentral.world")
    RESELLER_DOMAIN = os.environ.get("RESELLER_DOMAIN", "reseller.boostcentral.world")
    CLIENT_DOMAIN = os.environ.get("CLIENT_DOMAIN", "boostcentral.world")
    CLIENT_URL = os.environ.get("CLIENT_URL", "https://boostcentral.world")


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