"""
Gestion des fonctionnalites dev (activation admin + premium).
Mapping plan → features via table plans_fonctionnalites.
"""
import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


def _headers():
    key = current_app.config["SUPABASE_SERVICE_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _url(path):
    return current_app.config["SUPABASE_URL"] + "/rest/v1/" + path


def get_toutes_fonctionnalites():
    """Liste toutes les fonctionnalites dev (actives et inactives)."""
    try:
        r = requests.get(
            _url("fonctionnalites_dev?order=ordre"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_toutes_fonctionnalites: {type(e).__name__}")
        return []


def get_fonctionnalite(code):
    """Recupere une fonctionnalite par son code."""
    try:
        r = requests.get(
            _url(f"fonctionnalites_dev?code=eq.{code}&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_fonctionnalite: {type(e).__name__}")
        return None


def toggle_fonctionnalite(code, actif):
    try:
        r = requests.patch(
            _url(f"fonctionnalites_dev?code=eq.{code}"),
            json={"actif": actif},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_fonctionnalite: {type(e).__name__}")
        return False


def toggle_premium_fonctionnalite(code, est_premium):
    try:
        r = requests.patch(
            _url(f"fonctionnalites_dev?code=eq.{code}"),
            json={"est_premium": est_premium},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_premium_fonctionnalite: {type(e).__name__}")
        return False


def get_features_revendeur(revendeur_id):
    """Recupere les features activees manuellement par un revendeur (admin)."""
    try:
        r = requests.get(
            _url(f"revendeur_features?revendeur_id=eq.{revendeur_id}"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_features_revendeur: {type(e).__name__}")
        return []


def get_plan_features(plan_code):
    """Retourne la liste des feature_code accessibles pour un plan."""
    try:
        r = requests.get(
            _url(f"plans_fonctionnalites?plan_code=eq.{plan_code}&select=feature_code"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        if not isinstance(data, list):
            return set()
        return {row.get("feature_code") for row in data if row.get("feature_code")}
    except Exception as e:
        logger.error(f"get_plan_features: {type(e).__name__}")
        return set()


def _plan_a_feature(plan_code, feature_code):
    """Verifie si un plan donne acces a une feature."""
    if not plan_code or not feature_code:
        return False
    return feature_code in get_plan_features(plan_code)


def revendeur_a_feature(revendeur_id, code, profile=None):
    """
    Verifie si un revendeur a acces a une fonctionnalite.
    Logique :
    1. Feature inexistante ou inactive → False
    2. Admin → True (acces total)
    3. Feature non premium → True
    4. Feature premium :
       a. Verifier le mapping plan → features
       b. Sinon fallback : activation manuelle admin (revendeur_features)
    """
    feature = get_fonctionnalite(code)
    if not feature or not feature.get("actif"):
        return False

    if profile and profile.get("est_admin"):
        return True

    if not feature.get("est_premium"):
        return True

    # Mapping plan → feature
    niveau = (profile or {}).get("abonnement_niveau") or "gratuit"
    if _plan_a_feature(niveau, code):
        return True

    # Fallback : activation manuelle admin
    try:
        r = requests.get(
            _url(f"revendeur_features?revendeur_id=eq.{revendeur_id}&feature_code=eq.{code}&actif=eq.true&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return isinstance(data, list) and len(data) > 0
    except Exception as e:
        logger.error(f"revendeur_a_feature: {type(e).__name__}")
        return False


def activer_feature_revendeur(revendeur_id, code, actif=True):
    """Active manuellement une feature pour un revendeur (admin)."""
    try:
        existant = requests.get(
            _url(f"revendeur_features?revendeur_id=eq.{revendeur_id}&feature_code=eq.{code}&limit=1"),
            headers=_headers(), timeout=10
        ).json()

        if existant and isinstance(existant, list):
            r = requests.patch(
                _url(f"revendeur_features?id=eq.{existant[0]['id']}"),
                json={"actif": actif},
                headers=_headers(), timeout=10
            )
        else:
            r = requests.post(
                _url("revendeur_features"),
                json={"revendeur_id": revendeur_id, "feature_code": code, "actif": actif},
                headers=_headers(), timeout=10
            )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"activer_feature_revendeur: {type(e).__name__}")
        return False


def get_features_actives_pour_revendeur(revendeur_id, profile=None):
    """
    Retourne la liste des fonctionnalites dev accessibles a un revendeur.
    Admin → toutes les fonctionnalites actives.
    """
    toutes = get_toutes_fonctionnalites()
    est_admin = bool(profile.get("est_admin")) if profile else False

    resultat = []
    for f in toutes:
        if not f.get("actif"):
            continue
        if est_admin:
            resultat.append(f)
            continue
        if revendeur_a_feature(revendeur_id, f["code"], profile):
            resultat.append(f)
    return resultat