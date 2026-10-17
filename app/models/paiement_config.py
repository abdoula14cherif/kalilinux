"""
Gestion de la configuration des moyens de paiement des revendeurs.
SÉCURITÉ :
- Les clés API sont TOUJOURS chiffrées en DB (via crypto.py)
- Les clés ne sont JAMAIS loggées ni renvoyées en clair
- Seul le backend peut déchiffrer (avec ENCRYPTION_KEY)
"""
import logging
import requests
from datetime import datetime, timezone
from flask import current_app

from app.models.crypto import (
    chiffrer_dict,
    dechiffrer_dict,
    masquer,
    encrypt,
    decrypt,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# MÉTHODES SUPPORTÉES
# ═══════════════════════════════════════════════════════════════

METHODES_VALIDES = {
    # En ligne (API)
    "stripe": {
        "type": "en_ligne",
        "nom": "Stripe",
        "champs_requis": ["publishable_key", "secret_key", "webhook_secret"],
        "champs_secrets": ["secret_key", "webhook_secret"],
    },
    "leekpay": {
        "type": "en_ligne",
        "nom": "LeekPay",
        "champs_requis": ["public_key", "secret_key"],
        "champs_secrets": ["secret_key"],
    },
    "mysoleas": {
        "type": "en_ligne",
        "nom": "Mysoleas",
        "champs_requis": ["app_token", "webhook_secret"],
        "champs_secrets": ["app_token", "webhook_secret"],
    },
    # Mobile Money (manuel)
    "wave": {
        "type": "manuel",
        "nom": "Wave",
        "champs_requis": ["numero", "nom_titulaire"],
        "champs_secrets": [],
    },
    "orange_money": {
        "type": "manuel",
        "nom": "Orange Money",
        "champs_requis": ["numero", "nom_titulaire"],
        "champs_secrets": [],
    },
    "mtn_momo": {
        "type": "manuel",
        "nom": "MTN Mobile Money",
        "champs_requis": ["numero", "nom_titulaire"],
        "champs_secrets": [],
    },
    "moov": {
        "type": "manuel",
        "nom": "Moov Money",
        "champs_requis": ["numero", "nom_titulaire"],
        "champs_secrets": [],
    },
    "flooz": {
        "type": "manuel",
        "nom": "Togocom Flooz",
        "champs_requis": ["numero", "nom_titulaire"],
        "champs_secrets": [],
    },
    "free_money": {
        "type": "manuel",
        "nom": "Free Money",
        "champs_requis": ["numero", "nom_titulaire"],
        "champs_secrets": [],
    },
    "mpesa": {
        "type": "manuel",
        "nom": "M-Pesa",
        "champs_requis": ["numero", "nom_titulaire"],
        "champs_secrets": [],
    },
    "paystack": {
        "type": "en_ligne",
        "nom": "Paystack",
        "champs_requis": ["public_key", "secret_key"],
        "champs_secrets": ["secret_key"],
    },
    # Autres
    "cash": {
        "type": "cash",
        "nom": "Paiement a la livraison",
        "champs_requis": [],
        "champs_secrets": [],
    },
    "paylater": {
        "type": "credit",
        "nom": "Payer plus tard",
        "champs_requis": ["max_jours"],
        "champs_secrets": [],
    },
}


def _headers():
    key = current_app.config["SUPABASE_SERVICE_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _url(path):
    return current_app.config["SUPABASE_URL"] + "/rest/v1/" + path


# ═══════════════════════════════════════════════════════════════
# PAYS & MOYENS DISPONIBLES
# ═══════════════════════════════════════════════════════════════

def get_tous_pays():
    """Retourne la liste des 54 pays d'Afrique."""
    try:
        r = requests.get(
            _url("pays_afrique?actif=eq.true&order=ordre"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_tous_pays: {type(e).__name__}")
        return []


def get_pays_by_code(code):
    """Retourne un pays par son code ISO."""
    if not code or not isinstance(code, str):
        return None
    try:
        r = requests.get(
            _url(f"pays_afrique?code=eq.{code.upper()}&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_pays_by_code: {type(e).__name__}")
        return None


def get_moyens_pour_pays(pays_code):
    """Retourne tous les moyens disponibles pour un pays."""
    if not pays_code:
        return []
    try:
        r = requests.get(
            _url(f"pays_moyens_paiement?pays_code=eq.{pays_code}&actif=eq.true&order=ordre"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        if not isinstance(data, list):
            return []
        resultat = []
        for m in data:
            method_code = m.get("method")
            method_info = METHODES_VALIDES.get(method_code, {})
            resultat.append({
                "method": method_code,
                "nom_affiche": m.get("nom_affiche") or method_info.get("nom", method_code),
                "type": method_info.get("type", "inconnu"),
                "champs_requis": method_info.get("champs_requis", []),
                "champs_secrets": method_info.get("champs_secrets", []),
                "ordre": m.get("ordre", 99),
            })
        return resultat
    except Exception as e:
        logger.error(f"get_moyens_pour_pays: {type(e).__name__}")
        return []


# ═══════════════════════════════════════════════════════════════
# CONFIG PAIEMENT REVENDEUR
# ═══════════════════════════════════════════════════════════════

def get_config_revendeur(revendeur_id, method=None):
    """Récupère la config (CHIFFRÉE) d'un revendeur."""
    if not revendeur_id:
        return None if method else []
    try:
        if method:
            r = requests.get(
                _url(f"revendeur_paiement_methods?revendeur_id=eq.{revendeur_id}"
                     f"&method=eq.{method}&limit=1"),
                headers=_headers(), timeout=10
            )
            data = r.json()
            return data[0] if isinstance(data, list) and data else None
        else:
            r = requests.get(
                _url(f"revendeur_paiement_methods?revendeur_id=eq.{revendeur_id}"
                     f"&order=ordre"),
                headers=_headers(), timeout=10
            )
            data = r.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_config_revendeur: {type(e).__name__}")
        return None if method else []


def dechiffrer_config(config_row):
    """Déchiffre la config d'une ligne."""
    if not config_row:
        return {}
    encrypted = config_row.get("config_encrypted")
    if not encrypted:
        return {}
    return dechiffrer_dict(encrypted)


def get_config_decryptee(revendeur_id, method):
    """Retourne la config DÉCHIFFRÉE (backend)."""
    row = get_config_revendeur(revendeur_id, method)
    if not row:
        return None
    config = dechiffrer_config(row)
    if not config:
        return None
    return {
        "id": row.get("id"),
        "method": row.get("method"),
        "actif": row.get("actif"),
        "test_mode": row.get("test_mode"),
        "test_ok": row.get("test_ok"),
        "config": config,
    }


def get_config_decryptee_masquee(revendeur_id, method):
    """Retourne la config DÉCHIFFRÉE avec valeurs sensibles MASQUÉES."""
    row = get_config_revendeur(revendeur_id, method)
    if not row:
        return None
    config = dechiffrer_config(row)
    method_info = METHODES_VALIDES.get(method, {})
    champs_secrets = method_info.get("champs_secrets", [])

    config_masquee = {}
    for k, v in config.items():
        if k in champs_secrets and v:
            config_masquee[k] = masquer(v)
        else:
            config_masquee[k] = v

    return {
        "id": row.get("id"),
        "method": row.get("method"),
        "actif": row.get("actif"),
        "test_mode": row.get("test_mode"),
        "test_ok": row.get("test_ok"),
        "config": config_masquee,
    }


def save_config_revendeur(revendeur_id, method, config_data, actif=True):
    """Crée ou met à jour la config d'un revendeur."""
    if not revendeur_id or not method:
        return False, "Parametres manquants"
    if method not in METHODES_VALIDES:
        return False, "Methode invalide"
    if not isinstance(config_data, dict):
        return False, "Config invalide"

    methode_info = METHODES_VALIDES[method]
    champs_requis = methode_info.get("champs_requis", [])
    for champ in champs_requis:
        if not config_data.get(champ):
            return False, f"Champ requis manquant : {champ}"

    encrypted = chiffrer_dict(config_data)
    if not encrypted:
        return False, "Erreur de chiffrement"

    existing = get_config_revendeur(revendeur_id, method)

    payload = {
        "revendeur_id": revendeur_id,
        "method": method,
        "actif": bool(actif),
        "config_encrypted": encrypted,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        if existing:
            r = requests.patch(
                _url(f"revendeur_paiement_methods?id=eq.{existing['id']}"),
                json=payload,
                headers=_headers(), timeout=10
            )
        else:
            r = requests.post(
                _url("revendeur_paiement_methods"),
                json=payload,
                headers=_headers(), timeout=10
            )
        if r.status_code < 300:
            return True, None
        logger.error(f"save_config_revendeur HTTP {r.status_code}: {r.text[:200]}")
        return False, f"Erreur DB ({r.status_code})"
    except Exception as e:
        logger.error(f"save_config_revendeur: {type(e).__name__}")
        return False, "Erreur serveur"


def toggle_config_actif(revendeur_id, method, actif):
    """Active/désactive une méthode."""
    if not revendeur_id or method not in METHODES_VALIDES:
        return False
    existing = get_config_revendeur(revendeur_id, method)
    if not existing:
        return False
    try:
        r = requests.patch(
            _url(f"revendeur_paiement_methods?id=eq.{existing['id']}"),
            json={"actif": bool(actif), "updated_at": datetime.now(timezone.utc).isoformat()},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_config_actif: {type(e).__name__}")
        return False


def supprimer_config_revendeur(revendeur_id, method):
    """Supprime une config."""
    if not revendeur_id or not method:
        return False
    existing = get_config_revendeur(revendeur_id, method)
    if not existing:
        return False
    try:
        r = requests.delete(
            _url(f"revendeur_paiement_methods?id=eq.{existing['id']}"),
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_config_revendeur: {type(e).__name__}")
        return False


def maj_test_config(revendeur_id, method, test_ok):
    """Met à jour le statut de test."""
    existing = get_config_revendeur(revendeur_id, method)
    if not existing:
        return False
    try:
        r = requests.patch(
            _url(f"revendeur_paiement_methods?id=eq.{existing['id']}"),
            json={
                "test_ok": bool(test_ok),
                "test_le": datetime.now(timezone.utc).isoformat(),
            },
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"maj_test_config: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# MÉTHODES ACTIVES
# ═══════════════════════════════════════════════════════════════

def get_methodes_actives(revendeur_id):
    """Retourne les méthodes ACTIVES (backend)."""
    configs = get_config_revendeur(revendeur_id)
    if not configs:
        return []

    resultat = []
    for c in configs:
        if not c.get("actif"):
            continue
        method = c.get("method")
        if method not in METHODES_VALIDES:
            continue
        methode_info = METHODES_VALIDES[method]
        resultat.append({
            "method": method,
            "nom": methode_info.get("nom", method),
            "type": methode_info.get("type"),
            "config_row": c,
        })
    return resultat


def get_methodes_actives_pour_affichage(revendeur_id):
    """Retourne les méthodes ACTIVES pour affichage CLIENT."""
    actives = get_methodes_actives(revendeur_id)
    resultat = []

    for m in actives:
        method = m["method"]
        type_m = m["type"]
        config = dechiffrer_config(m["config_row"])
        methode_info = METHODES_VALIDES[method]

        item = {
            "method": method,
            "nom": methode_info.get("nom", method),
            "type": type_m,
        }

        if type_m == "manuel":
            item["numero"] = config.get("numero")
            item["nom_titulaire"] = config.get("nom_titulaire")

        if type_m == "cash":
            item["instructions"] = "Paiement a la livraison"

        if type_m == "credit":
            item["max_jours"] = config.get("max_jours", 30)

        resultat.append(item)

    return resultat


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def methode_est_valide(method):
    return method in METHODES_VALIDES


def get_info_methode(method):
    return METHODES_VALIDES.get(method)


# ═══════════════════════════════════════════════════════════════
# LOG ACCÈS ADMIN
# ═══════════════════════════════════════════════════════════════

def log_admin_key_access(admin_id, revendeur_id, method, raison, ip=None):
    """Log OBLIGATOIRE quand un admin révèle une clé API."""
    try:
        payload = {
            "admin_id": admin_id,
            "revendeur_id": revendeur_id,
            "method": method,
            "raison": (raison or "")[:500],
            "ip": (ip or "")[:45] or None,
        }
        requests.post(
            _url("admin_key_access_logs"),
            json=payload,
            headers=_headers(), timeout=10
        )
    except Exception as e:
        logger.error(f"log_admin_key_access: {type(e).__name__}")


def get_admin_key_access_logs(limit=200):
    """Récupère les logs d'accès."""
    try:
        limit = max(1, min(int(limit), 500))
        r = requests.get(
            _url(f"admin_key_access_logs?order=created_at.desc&limit={limit}"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_admin_key_access_logs: {type(e).__name__}")
        return []