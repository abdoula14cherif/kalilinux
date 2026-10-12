"""
Fonctions Supabase pour le site reseller.
Utilise la meme base que boostcentral.
"""
import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def _headers(admin=False):
    key = current_app.config["SUPABASE_SERVICE_KEY"] if admin else current_app.config["SUPABASE_ANON_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _url(path):
    return current_app.config["SUPABASE_URL"] + "/rest/v1/" + path


def get_profile(user_id):
    """Recupere un profil par son ID."""
    try:
        r = requests.get(_url(f"profiles?id=eq.{user_id}&limit=1"), headers=_headers(True))
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile: {e}")
        return None


def get_profile_by_email(email):
    """Recupere un profil par email."""
    try:
        r = requests.get(_url(f"profiles?email=eq.{email}&limit=1"), headers=_headers(True))
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile_by_email: {e}")
        return None


def update_profile(user_id, data):
    """Met a jour un profil."""
    try:
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"), json=data, headers=_headers(True))
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_profile: {e}")
        return False