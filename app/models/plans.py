"""
Gestion des plans d'abonnement et des limites (freemium).
Plans : Gratuit / Pro / Business
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


# ═══════════════════════════════════════════════════════════════
# PLANS - LECTURE
# ═══════════════════════════════════════════════════════════════

def lister_plans(actif_only=True):
    """Liste tous les plans d'abonnement (actifs ou tous)."""
    try:
        url = "abonnements_plans?order=ordre"
        if actif_only:
            url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"lister_plans: {type(e).__name__}")
        return []


def get_plan(code):
    """Recupere un plan par son code."""
    try:
        r = requests.get(
            _url(f"abonnements_plans?code=eq.{code}&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_plan: {type(e).__name__}")
        return None


def get_plan_du_revendeur(profile):
    """Recupere le plan actuel d'un revendeur (avec fallback gratuit)."""
    code = (profile or {}).get("abonnement_niveau") or "gratuit"
    plan = get_plan(code)
    if not plan:
        plan = get_plan("gratuit")
    return plan or {}


# ═══════════════════════════════════════════════════════════════
# LIMITES
# ═══════════════════════════════════════════════════════════════

LIMITES_MAP = {
    "produits": "max_produits",
    "categories": "max_categories",
    "bannieres": "max_bannieres",
    "attributs": "max_attributs",
    "coupons": "max_coupons",
}


def check_limite(profile, type_ressource, count_actuel=0):
    """
    Verifie si un revendeur peut ajouter une ressource supplementaire.
    Retourne (peut_ajouter, limite_max, count_actuel).
    """
    plan = get_plan_du_revendeur(profile)
    cle = LIMITES_MAP.get(type_ressource)
    if not cle:
        return True, 999999, count_actuel

    max_autorise = plan.get(cle) or 0
    if max_autorise >= 999999:
        return True, 999999, count_actuel
    if max_autorise == 0:
        return False, 0, count_actuel

    return count_actuel < max_autorise, max_autorise, count_actuel


def message_limite(type_ressource, plan):
    """Genere un message d'erreur quand la limite est atteinte."""
    labels = {
        "produits": "produits",
        "categories": "categories",
        "bannieres": "bannieres",
        "attributs": "attributs",
        "coupons": "coupons",
    }
    label = labels.get(type_ressource, type_ressource)
    plan_nom = plan.get("nom") or "Gratuit"
    return (
        f"Limite atteinte pour votre plan {plan_nom}. "
        f"Vous ne pouvez pas ajouter plus de {label}. "
        f"Passez au plan Pro ou Business pour en ajouter plus."
    )


def peut_utiliser_feature(profile, feature_code):
    """
    Verifie si un revendeur peut utiliser une fonctionnalite.
    Retourne True ou False.
    """
    plan = get_plan_du_revendeur(profile)
    code_plan = plan.get("code") or "gratuit"

    # Business uniquement
    if feature_code in ("webhooks", "oauth_apps", "api_keys"):
        return code_plan == "business"

    # Pro + Business
    if feature_code in ("sdk", "playground", "logs_api",
                        "notifications_email", "notifications_whatsapp",
                        "avis_clients", "badge_verifie"):
        return code_plan in ("pro", "business")

    # Accessible a tous
    if feature_code in ("documentation", "produits", "categories",
                        "bannieres", "attributs"):
        return True

    return False


def get_commission_pct(profile):
    """Retourne le pourcentage de commission du plan du revendeur."""
    plan = get_plan_du_revendeur(profile)
    try:
        return float(plan.get("commission_pct") or 0.10)
    except Exception:
        return 0.10


# ═══════════════════════════════════════════════════════════════
# CHANGEMENT DE PLAN
# ═══════════════════════════════════════════════════════════════

def changer_plan(user_id, plan_code):
    """Change le plan d'un revendeur."""
    from app.models.database import update_profile
    plan = get_plan(plan_code)
    if not plan or not plan.get("actif"):
        return False
    return update_profile(user_id, {"abonnement_niveau": plan_code})


# ═══════════════════════════════════════════════════════════════
# ADMIN - GESTION DES PLANS
# ═══════════════════════════════════════════════════════════════

def creer_plan_admin(data):
    """Cree un nouveau plan (admin)."""
    try:
        # Verifier que le code n'existe pas
        existant = get_plan(data.get("code", ""))
        if existant:
            return None, "Le code existe deja"

        r = requests.post(
            _url("abonnements_plans"),
            json=data,
            headers=_headers(), timeout=10
        )
        if r.status_code in (200, 201):
            result = r.json()
            return (result[0] if isinstance(result, list) and result else None), None
        return None, f"Erreur HTTP {r.status_code}"
    except Exception as e:
        logger.error(f"creer_plan_admin: {type(e).__name__}")
        return None, "Erreur serveur"


def modifier_plan_admin(plan_id, data):
    """Modifie un plan existant (admin)."""
    try:
        r = requests.patch(
            _url(f"abonnements_plans?id=eq.{plan_id}"),
            json=data,
            headers=_headers(), timeout=10
        )
        return r.status_code < 300, None if r.status_code < 300 else f"Erreur {r.status_code}"
    except Exception as e:
        logger.error(f"modifier_plan_admin: {type(e).__name__}")
        return False, "Erreur serveur"


def toggle_plan_admin(plan_id, actif):
    """Active/desactive un plan (admin)."""
    try:
        r = requests.patch(
            _url(f"abonnements_plans?id=eq.{plan_id}"),
            json={"actif": actif},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_plan_admin: {type(e).__name__}")
        return False


def supprimer_plan_admin(plan_id):
    """Supprime un plan (admin). Impossible si c'est le plan par defaut."""
    try:
        # Ne pas supprimer le plan gratuit
        plan = requests.get(
            _url(f"abonnements_plans?id=eq.{plan_id}&limit=1"),
            headers=_headers(), timeout=10
        ).json()
        if plan and plan[0].get("code") == "gratuit":
            return False, "Impossible de supprimer le plan Gratuit"

        r = requests.delete(
            _url(f"abonnements_plans?id=eq.{plan_id}"),
            headers=_headers(), timeout=10
        )
        return r.status_code < 300, None if r.status_code < 300 else f"Erreur {r.status_code}"
    except Exception as e:
        logger.error(f"supprimer_plan_admin: {type(e).__name__}")
        return False, "Erreur serveur"


def get_plan_by_id(plan_id):
    """Recupere un plan par son ID."""
    try:
        r = requests.get(
            _url(f"abonnements_plans?id=eq.{plan_id}&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_plan_by_id: {type(e).__name__}")
        return None