"""
Modele admin — Gestion globale de la plateforme.
"""
import logging
from datetime import datetime, timezone
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
# LOGS ADMIN
# ═══════════════════════════════════════════════════════════════

def log_admin_action(admin_id, action, cible_type=None, cible_id=None, details=None, ip=None):
    """Enregistre une action admin pour audit."""
    try:
        payload = {
            "admin_id": admin_id,
            "action": action[:100],
            "cible_type": cible_type,
            "cible_id": cible_id,
            "details": details or {},
            "ip": ip,
        }
        requests.post(_url("admin_logs"), json=payload, headers=_headers(), timeout=10)
    except Exception as e:
        logger.error(f"log_admin_action: {type(e).__name__}")


def get_admin_logs(limit=100):
    """Recupere les derniers logs admin."""
    try:
        r = requests.get(
            _url(f"admin_logs?order=created_at.desc&limit={limit}"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_admin_logs: {type(e).__name__}")
        return []


# ═══════════════════════════════════════════════════════════════
# STATS GLOBALES
# ═══════════════════════════════════════════════════════════════

def get_stats_globales():
    """Statistiques globales de la plateforme."""
    try:
        r = requests.get(_url("profiles?limit=10000"), headers=_headers(), timeout=15)
        profiles = r.json() if r.status_code < 300 else []
        if not isinstance(profiles, list):
            profiles = []

        revendeurs = [p for p in profiles if p.get("est_revendeur")]
        admins = [p for p in profiles if p.get("est_admin")]
        bannis = [p for p in profiles if p.get("banni")]

        r2 = requests.get(_url("boutique_commandes?limit=10000"), headers=_headers(), timeout=15)
        commandes = r2.json() if r2.status_code < 300 else []
        if not isinstance(commandes, list):
            commandes = []

        commandes_livrees = [c for c in commandes if c.get("statut") == "livree"]
        revenus_total = sum(c.get("total", 0) or 0 for c in commandes_livrees)

        # Commissions collectees par la plateforme
        commissions_total = 0
        try:
            r3 = requests.get(_url("revendeur_gains?select=commission"), headers=_headers(), timeout=15)
            gains = r3.json() if r3.status_code < 300 else []
            if isinstance(gains, list):
                commissions_total = sum(g.get("commission", 0) or 0 for g in gains)
        except Exception:
            pass

        # Repartition par plan
        plans_count = {"gratuit": 0, "pro": 0, "business": 0}
        for p in revendeurs:
            niveau = p.get("abonnement_niveau") or "gratuit"
            if niveau in plans_count:
                plans_count[niveau] += 1

        return {
            "nb_utilisateurs": len(profiles),
            "nb_revendeurs": len(revendeurs),
            "nb_admins": len(admins),
            "nb_bannis": len(bannis),
            "nb_commandes": len(commandes),
            "nb_commandes_livrees": len(commandes_livrees),
            "revenus_total": revenus_total,
            "commissions_total": commissions_total,
            "plans_count": plans_count,
        }
    except Exception as e:
        logger.error(f"get_stats_globales: {type(e).__name__}")
        return {
            "nb_utilisateurs": 0, "nb_revendeurs": 0, "nb_admins": 0,
            "nb_bannis": 0, "nb_commandes": 0, "nb_commandes_livrees": 0,
            "revenus_total": 0, "commissions_total": 0,
            "plans_count": {"gratuit": 0, "pro": 0, "business": 0},
        }


# ═══════════════════════════════════════════════════════════════
# GESTION DES UTILISATEURS
# ═══════════════════════════════════════════════════════════════

def get_tous_utilisateurs(limit=500, search=None):
    """Liste tous les utilisateurs (avec recherche optionnelle)."""
    try:
        url = f"profiles?order=created_at.desc&limit={limit}"
        if search:
            url += f"&or=(email.ilike.*{search}*,full_name.ilike.*{search}*)"
        r = requests.get(_url(url), headers=_headers(), timeout=15)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_tous_utilisateurs: {type(e).__name__}")
        return []


def bannir_utilisateur(user_id, raison=None):
    """Bannit un utilisateur."""
    try:
        payload = {
            "banni": True,
            "banni_raison": raison[:500] if raison else None,
            "banni_le": datetime.now(timezone.utc).isoformat(),
        }
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"), json=payload, headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"bannir_utilisateur: {type(e).__name__}")
        return False


def debannir_utilisateur(user_id):
    """Debannit un utilisateur."""
    try:
        payload = {"banni": False, "banni_raison": None, "banni_le": None}
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"), json=payload, headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"debannir_utilisateur: {type(e).__name__}")
        return False


def promouvoir_admin(user_id, est_admin=True):
    """Promeut ou retrograde un utilisateur admin."""
    try:
        r = requests.patch(
            _url(f"profiles?id=eq.{user_id}"),
            json={"est_admin": est_admin},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"promouvoir_admin: {type(e).__name__}")
        return False


def modifier_balance(user_id, nouveau_montant):
    """Modifie le solde d'un utilisateur (admin override)."""
    try:
        r = requests.patch(
            _url(f"profiles?id=eq.{user_id}"),
            json={"balance": float(nouveau_montant)},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"modifier_balance: {type(e).__name__}")
        return False


def modifier_abonnement(user_id, niveau):
    """
    Change l'abonnement d'un revendeur (admin override).
    Met aussi a jour la commission du revendeur selon le plan.
    """
    valides = ("gratuit", "pro", "business")
    if niveau not in valides:
        return False
    try:
        # Recuperer la commission du plan cible
        commission_pct = 0.10
        try:
            r_plan = requests.get(
                _url(f"abonnements_plans?code=eq.{niveau}&limit=1"),
                headers=_headers(), timeout=10
            )
            plans = r_plan.json()
            if isinstance(plans, list) and plans:
                commission_pct = float(plans[0].get("commission_pct", 0.10))
        except Exception:
            pass

        payload = {
            "abonnement_niveau": niveau,
            "revendeur_commission_pct": commission_pct,
        }
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"), json=payload, headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"modifier_abonnement: {type(e).__name__}")
        return False


def supprimer_utilisateur(user_id):
    """Supprime un utilisateur et toutes ses donnees."""
    try:
        r = requests.delete(_url(f"profiles?id=eq.{user_id}"), headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_utilisateur: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# FONCTIONNALITES DEV (modification avancee)
# ═══════════════════════════════════════════════════════════════

def modifier_fonctionnalite(code, data):
    """Modifie une fonctionnalite (nom, icone, couleur, ordre...)."""
    try:
        autorises = {"nom", "description", "icone", "couleur", "est_premium", "actif", "ordre"}
        payload = {k: v for k, v in data.items() if k in autorises}
        if not payload:
            return False
        r = requests.patch(
            _url(f"fonctionnalites_dev?code=eq.{code}"),
            json=payload, headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"modifier_fonctionnalite: {type(e).__name__}")
        return False


def creer_fonctionnalite(data):
    """Cree une nouvelle fonctionnalite."""
    try:
        r = requests.post(_url("fonctionnalites_dev"), json=data, headers=_headers(), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"creer_fonctionnalite: {type(e).__name__}")
        return None


def supprimer_fonctionnalite(code):
    """Supprime une fonctionnalite."""
    try:
        r = requests.delete(_url(f"fonctionnalites_dev?code=eq.{code}"), headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_fonctionnalite: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# PLANS — gestion admin
# ═══════════════════════════════════════════════════════════════

def modifier_plan(code, data):
    """Modifie un plan d'abonnement (admin)."""
    try:
        autorises = {
            "nom", "description", "prix_mensuel", "couleur", "icone",
            "max_produits", "max_categories", "max_bannieres",
            "max_attributs", "max_coupons", "commission_pct",
            "avantages", "actif", "ordre", "populaire"
        }
        payload = {k: v for k, v in data.items() if k in autorises}
        if not payload:
            return False
        r = requests.patch(
            _url(f"abonnements_plans?code=eq.{code}"),
            json=payload, headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"modifier_plan: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS GLOBALES
# ═══════════════════════════════════════════════════════════════

def creer_notification_globale(titre, message, type_notif="info"):
    """Cree une notification globale visible par tous."""
    try:
        payload = {
            "titre": titre[:100],
            "message": message[:500],
            "type": type_notif,
            "actif": True,
        }
        r = requests.post(_url("notifications_globales"), json=payload, headers=_headers(), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"creer_notification_globale: {type(e).__name__}")
        return None


def get_notifications_globales(actif_only=True):
    """Liste les notifications globales."""
    try:
        url = "notifications_globales?order=created_at.desc"
        if actif_only:
            url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_notifications_globales: {type(e).__name__}")
        return []


def toggle_notification_globale(notif_id, actif):
    """Active/desactive une notification globale."""
    try:
        r = requests.patch(
            _url(f"notifications_globales?id=eq.{notif_id}"),
            json={"actif": actif},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_notification_globale: {type(e).__name__}")
        return False


def supprimer_notification_globale(notif_id):
    """Supprime une notification globale."""
    try:
        r = requests.delete(_url(f"notifications_globales?id=eq.{notif_id}"), headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_notification_globale: {type(e).__name__}")
        return False