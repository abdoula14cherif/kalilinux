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


# ═══════════════════════════════════════════════════════════════
# PROFIL
# ═══════════════════════════════════════════════════════════════

def get_profile(user_id):
    try:
        r = requests.get(_url(f"profiles?id=eq.{user_id}&limit=1"), headers=_headers(True))
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile: {e}")
        return None


def get_profile_by_email(email):
    try:
        r = requests.get(_url(f"profiles?email=eq.{email}&limit=1"), headers=_headers(True))
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile_by_email: {e}")
        return None


def get_profile_by_slug(slug):
    """Recupere un profil revendeur par son slug (boutique publique)."""
    try:
        r = requests.get(
            _url(f"profiles?revendeur_slug=eq.{slug}&est_revendeur=eq.true&limit=1"),
            headers=_headers(True)
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile_by_slug: {e}")
        return None


def update_profile(user_id, data):
    """Met a jour un profil."""
    try:
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"), json=data, headers=_headers(True))
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_profile: {e}")
        return False


def debit_balance(user_id, montant):
    try:
        profile = get_profile(user_id)
        if not profile:
            return None
        balance = profile.get("balance", 0) or 0
        if balance < montant:
            return None
        new_balance = balance - montant
        ok = update_profile(user_id, {"balance": new_balance})
        return new_balance if ok else None
    except Exception as e:
        logger.error(f"debit_balance: {e}")
        return None


def credit_balance(user_id, montant):
    try:
        profile = get_profile(user_id)
        if not profile:
            return None
        new_balance = (profile.get("balance", 0) or 0) + montant
        ok = update_profile(user_id, {"balance": new_balance})
        return new_balance if ok else None
    except Exception as e:
        logger.error(f"credit_balance: {e}")
        return None


def slug_deja_pris(slug):
    try:
        r = requests.get(_url(f"profiles?revendeur_slug=eq.{slug}&limit=1"), headers=_headers(True))
        data = r.json()
        return isinstance(data, list) and len(data) > 0
    except Exception as e:
        logger.error(f"slug_deja_pris: {e}")
        return True


def activer_revendeur(user_id, slug, modele, commission_pct=0.10):
    return update_profile(user_id, {
        "est_revendeur": True,
        "revendeur_slug": slug,
        "revendeur_modele": modele,
        "revendeur_commission_pct": commission_pct if modele == "commission" else 0.0,
        "boutique_active": True,
    })


def toggle_boutique_active(revendeur_id, active):
    """Active ou desactive une boutique (usage admin)."""
    try:
        r = requests.patch(
            _url(f"profiles?id=eq.{revendeur_id}"),
            json={"boutique_active": active},
            headers=_headers(True)
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_boutique_active: {e}")
        return False


def get_all_revendeurs(limit=200):
    """Liste tous les revendeurs (pour l'admin)."""
    try:
        r = requests.get(
            _url(f"profiles?est_revendeur=eq.true&order=created_at.desc&limit={limit}"),
            headers=_headers(True)
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_all_revendeurs: {e}")
        return []


def incrementer_visite_boutique(revendeur_id):
    """Incremente le compteur de visites d'une boutique."""
    try:
        r = requests.get(_url(f"profiles?id=eq.{revendeur_id}&select=boutique_visites"), headers=_headers(True))
        data = r.json()
        if data:
            actuel = (data[0].get("boutique_visites") or 0) + 1
            requests.patch(_url(f"profiles?id=eq.{revendeur_id}"), json={"boutique_visites": actuel}, headers=_headers(True))
            return actuel
        return 0
    except Exception as e:
        logger.error(f"incrementer_visite_boutique: {e}")
        return 0


# ═══════════════════════════════════════════════════════════════
# SERVICES
# ═══════════════════════════════════════════════════════════════

def get_active_services(network=None):
    try:
        if network:
            url = _url(f"services?actif=eq.true&reseau=eq.{network}&order=categorie")
        else:
            url = _url("services?actif=eq.true&order=reseau,categorie")
        r = requests.get(url, headers=_headers(True))
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_active_services: {e}")
        return []


def get_service_by_id(service_id):
    try:
        r = requests.get(_url(f"services?id=eq.{service_id}&limit=1"), headers=_headers(True))
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_service_by_id: {e}")
        return None


# ═══════════════════════════════════════════════════════════════
# PRIX REVENDEUR
# ═══════════════════════════════════════════════════════════════

def get_revendeur_prix_all(revendeur_id):
    try:
        r = requests.get(_url(f"revendeur_prix?revendeur_id=eq.{revendeur_id}"), headers=_headers(True))
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_revendeur_prix_all: {e}")
        return []


def get_revendeur_prix(revendeur_id, service_id):
    try:
        r = requests.get(_url(f"revendeur_prix?revendeur_id=eq.{revendeur_id}&service_id=eq.{service_id}&limit=1"), headers=_headers(True))
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_revendeur_prix: {e}")
        return None


def set_revendeur_prix(revendeur_id, service_id, prix_fcfa):
    existing = get_revendeur_prix(revendeur_id, service_id)
    try:
        if existing:
            r = requests.patch(
                _url(f"revendeur_prix?id=eq.{existing['id']}"),
                json={"prix_fcfa": prix_fcfa},
                headers=_headers(True)
            )
        else:
            r = requests.post(
                _url("revendeur_prix"),
                json={"revendeur_id": revendeur_id, "service_id": service_id, "prix_fcfa": prix_fcfa},
                headers=_headers(True)
            )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"set_revendeur_prix: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# CLIENTS REVENDEUR
# ═══════════════════════════════════════════════════════════════

def get_revendeur_clients(revendeur_id):
    try:
        r = requests.get(_url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}"), headers=_headers(True))
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_revendeur_clients: {e}")
        return []


def get_revendeur_clients_detail(revendeur_id):
    try:
        r = requests.get(
            _url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}&order=created_at.desc"),
            headers=_headers(True)
        )
        liens = r.json()
        if not isinstance(liens, list):
            return []
        resultat = []
        for l in liens:
            profil = get_profile(l.get("client_id"))
            if profil:
                resultat.append({
                    "id": profil.get("id"),
                    "email": profil.get("email"),
                    "full_name": profil.get("full_name"),
                    "balance": profil.get("balance", 0),
                    "country": profil.get("country"),
                    "rattache_le": l.get("created_at"),
                })
        return resultat
    except Exception as e:
        logger.error(f"get_revendeur_clients_detail: {e}")
        return []


def rattacher_client_revendeur(revendeur_id, client_id):
    try:
        exist = requests.get(
            _url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}&client_id=eq.{client_id}&limit=1"),
            headers=_headers(True)
        ).json()
        if exist:
            return True
        r = requests.post(
            _url("revendeur_clients"),
            json={"revendeur_id": revendeur_id, "client_id": client_id},
            headers=_headers(True)
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"rattacher_client_revendeur: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# COMMANDES REVENDEUR
# ═══════════════════════════════════════════════════════════════

def get_revendeur_orders(revendeur_id, limit=100):
    try:
        r = requests.get(
            _url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}&select=client_id"),
            headers=_headers(True)
        )
        liens = r.json()
        client_ids = [l.get("client_id") for l in liens] if isinstance(liens, list) else []
        if not client_ids:
            return []
        ids_str = ",".join(client_ids)
        r2 = requests.get(
            _url(f"commandes?user_id=in.({ids_str})&order=created_at.desc&limit={limit}"),
            headers=_headers(True)
        )
        data = r2.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_revendeur_orders: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
# GAINS REVENDEUR
# ═══════════════════════════════════════════════════════════════

def get_revendeur_gains_total(revendeur_id):
    try:
        r = requests.get(
            _url(f"revendeur_gains?revendeur_id=eq.{revendeur_id}&select=montant"),
            headers=_headers(True)
        )
        data = r.json()
        return sum(g.get("montant", 0) or 0 for g in data) if isinstance(data, list) else 0
    except Exception as e:
        logger.error(f"get_revendeur_gains_total: {e}")
        return 0