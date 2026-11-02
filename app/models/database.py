"""
Fonctions Supabase pour le site reseller.
Inclut la gestion des profils, produits, commandes, wallet et retraits.
"""
import logging
import re
from datetime import datetime, timezone
import requests
from flask import current_app

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# SEUILS CREDIT BOOST
# ═══════════════════════════════════════════════════════════════
SEUIL_CREDIT_MIN_PUBLICATION = 2000
SEUIL_CREDIT_ALERTE = 2000
SEUIL_CREDIT_PAUSE = 500


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
        r = requests.get(_url(f"profiles?id=eq.{user_id}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile: {type(e).__name__}")
        return None


def get_profile_by_email(email):
    try:
        r = requests.get(_url(f"profiles?email=eq.{email}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile_by_email: {type(e).__name__}")
        return None


def get_profile_by_slug(slug):
    try:
        r = requests.get(
            _url(f"profiles?revendeur_slug=eq.{slug}&est_revendeur=eq.true&limit=1"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile_by_slug: {type(e).__name__}")
        return None


def update_profile(user_id, data):
    try:
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_profile: {type(e).__name__}")
        return False


def slug_deja_pris(slug):
    try:
        r = requests.get(_url(f"profiles?revendeur_slug=eq.{slug}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return isinstance(data, list) and len(data) > 0
    except Exception as e:
        logger.error(f"slug_deja_pris: {type(e).__name__}")
        return True


def activer_revendeur(user_id, slug):
    try:
        profile = get_profile(user_id)
        commission_pct = 0.10
        if profile:
            plan_code = profile.get("abonnement_niveau") or "gratuit"
            plan = get_plan_by_code(plan_code)
            if plan:
                commission_pct = float(plan.get("commission_pct", 0.10))

        return update_profile(user_id, {
            "est_revendeur": True,
            "revendeur_slug": slug,
            "revendeur_commission_pct": commission_pct,
            "boutique_active": True,
        })
    except Exception as e:
        logger.error(f"activer_revendeur: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# PAYS DU REVENDEUR (VERROUILLÉ)
# ═══════════════════════════════════════════════════════════════

def set_pays_revendeur(user_id, pays_code):
    try:
        profile = get_profile(user_id)
        if not profile:
            return False, "Utilisateur introuvable"

        if profile.get("pays_verrouille"):
            return False, "Pays deja verrouille."

        if not pays_code:
            return False, "Code pays manquant"

        pays_code = pays_code.upper().strip()
        if not re.match(r"^[A-Z]{2}$", pays_code):
            return False, "Code pays invalide"

        ok = update_profile(user_id, {
            "pays_code": pays_code,
            "pays_verrouille": True,
            "pays_verrouille_le": datetime.now(timezone.utc).isoformat(),
        })
        return (True, None) if ok else (False, "Erreur de sauvegarde")
    except Exception as e:
        logger.error(f"set_pays_revendeur: {type(e).__name__}")
        return False, "Erreur serveur"


def get_pays_revendeur(user_id):
    try:
        profile = get_profile(user_id)
        if not profile:
            return None
        return profile.get("pays_code")
    except Exception as e:
        logger.error(f"get_pays_revendeur: {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# PLANS D'ABONNEMENT
# ═══════════════════════════════════════════════════════════════

def get_abonnements_plans():
    try:
        r = requests.get(_url("abonnements_plans?actif=eq.true&order=ordre"), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_abonnements_plans: {type(e).__name__}")
        return []


def get_plan_by_code(code):
    try:
        r = requests.get(
            _url(f"abonnements_plans?code=eq.{code}&limit=1"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_plan_by_code: {type(e).__name__}")
        return None


def get_plan_actuel(profile):
    code = (profile or {}).get("abonnement_niveau") or "gratuit"
    plan = get_plan_by_code(code)
    if not plan:
        plan = get_plan_by_code("gratuit")
    return plan


def get_commission_pct(profile):
    if profile and profile.get("revendeur_commission_pct") is not None:
        return float(profile["revendeur_commission_pct"])
    plan = get_plan_actuel(profile)
    return float((plan or {}).get("commission_pct", 0.10))


# ═══════════════════════════════════════════════════════════════
# CRÉDIT BOOST & WALLET (PORTEFEUILLE INTERNE)
# ═══════════════════════════════════════════════════════════════

def get_credit_boost(user_id):
    try:
        profile = get_profile(user_id)
        if not profile:
            return 0
        return float(profile.get("credit_boost", 0) or 0)
    except Exception as e:
        logger.error(f"get_credit_boost: {type(e).__name__}")
        return 0


def get_solde_wallet(user_id):
    """Retourne le solde retirable du portefeuille interne."""
    try:
        profile = get_profile(user_id)
        if not profile:
            return 0
        return float(profile.get("solde_wallet", 0) or 0)
    except Exception as e:
        logger.error(f"get_solde_wallet: {type(e).__name__}")
        return 0


def credit_boost_suffisant(profile):
    if not profile:
        return False
    return float(profile.get("credit_boost", 0) or 0) >= SEUIL_CREDIT_MIN_PUBLICATION


def _log_credit_boost_transaction(revendeur_id, type_tx, montant, solde_apres,
                                   description=None, source_type=None,
                                   source_id=None, metadata=None):
    try:
        payload = {
            "revendeur_id": revendeur_id,
            "type": type_tx,
            "montant": montant,
            "solde_apres": solde_apres,
            "description": description,
            "source_type": source_type,
            "source_id": source_id,
            "metadata": metadata or {},
        }
        requests.post(_url("credit_boost_transactions"), json=payload,
                     headers=_headers(True), timeout=10)
    except Exception as e:
        logger.error(f"_log_credit_boost_transaction: {type(e).__name__}")


def debiter_credit_boost(user_id, montant, description=None,
                        source_type=None, source_id=None, metadata=None):
    try:
        profile = get_profile(user_id)
        if not profile:
            return None
        solde_actuel = float(profile.get("credit_boost", 0) or 0)
        nouveau_solde = solde_actuel - float(montant)

        ok = update_profile(user_id, {"credit_boost": nouveau_solde})
        if ok:
            _log_credit_boost_transaction(
                user_id, "debit_commission", -abs(float(montant)),
                nouveau_solde, description, source_type, source_id, metadata
            )
            return nouveau_solde
        return None
    except Exception as e:
        logger.error(f"debiter_credit_boost: {type(e).__name__}")
        return None


def crediter_credit_boost(user_id, montant, description=None,
                         source_type=None, source_id=None, metadata=None):
    try:
        profile = get_profile(user_id)
        if not profile:
            return None
        solde_actuel = float(profile.get("credit_boost", 0) or 0)
        nouveau_solde = solde_actuel + float(montant)

        ok = update_profile(user_id, {"credit_boost": nouveau_solde})
        if ok:
            _log_credit_boost_transaction(
                user_id, "recharge", float(montant),
                nouveau_solde, description, source_type, source_id, metadata
            )
            reactiver_boutique_si_solde_ok(user_id)
            return nouveau_solde
        return None
    except Exception as e:
        logger.error(f"crediter_credit_boost: {type(e).__name__}")
        return None


def reactiver_boutique_si_solde_ok(user_id):
    try:
        profile = get_profile(user_id)
        if not profile:
            return False
        if not profile.get("est_revendeur"):
            return False
        if profile.get("boutique_active"):
            return True

        credit_actuel = float(profile.get("credit_boost", 0) or 0)
        if credit_actuel >= SEUIL_CREDIT_PAUSE:
            update_profile(user_id, {"boutique_active": True})
            logger.info(f"[REACTIVATION] Boutique {user_id} reactivee.")
            return True
        return False
    except Exception as e:
        logger.error(f"reactiver_boutique_si_solde_ok: {type(e).__name__}")
        return False


def get_transactions_credit_boost(user_id, limit=100):
    try:
        r = requests.get(
            _url(f"credit_boost_transactions?revendeur_id=eq.{user_id}"
                 f"&order=created_at.desc&limit={limit}"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_transactions_credit_boost: {type(e).__name__}")
        return []


# ═══════════════════════════════════════════════════════════════
# RETRAITS (WALLET)
# ═══════════════════════════════════════════════════════════════

def create_demande_retrait(data):
    """Crée une demande de retrait."""
    try:
        r = requests.post(_url("demandes_retrait"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_demande_retrait: {type(e).__name__}")
        return None


def get_demande_retrait(demande_id):
    """Récupère une demande de retrait par son ID."""
    try:
        r = requests.get(
            _url(f"demandes_retrait?id=eq.{demande_id}&limit=1"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_demande_retrait: {type(e).__name__}")
        return None


def get_demandes_retrait_par_revendeur(revendeur_id):
    """Récupère l'historique des retraits d'un revendeur."""
    try:
        r = requests.get(
            _url(f"demandes_retrait?revendeur_id=eq.{revendeur_id}&order=created_at.desc"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_demandes_retrait_par_revendeur: {type(e).__name__}")
        return []


def update_demande_retrait(demande_id, data):
    """Met à jour le statut d'une demande de retrait."""
    try:
        r = requests.patch(
            _url(f"demandes_retrait?id=eq.{demande_id}"),
            json=data, headers=_headers(True), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_demande_retrait: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# APPLICATION DE LA COMMISSION
# ═══════════════════════════════════════════════════════════════

def appliquer_commission_commande(commande, profile=None):
    try:
        if not commande:
            return None

        revendeur_id = commande.get("revendeur_id")
        if not revendeur_id:
            return None

        if commande.get("commission_appliquee"):
            return {"succes": True, "deja_appliquee": True}

        if not profile:
            profile = get_profile(revendeur_id)
        if not profile:
            return None

        total = float(commande.get("total", 0) or 0)
        if total <= 0:
            return None

        commission_pct = float(profile.get("revendeur_commission_pct", 0.10) or 0.10)
        commission = round(total * commission_pct, 2)
        montant_net = round(total - commission, 2)

        # 1. Debiter le credit_boost
        nouveau_credit = debiter_credit_boost(
            revendeur_id, commission,
            description=f"Commission commande {commande.get('reference')}",
            source_type="commande_boutique",
            source_id=str(commande.get("id")),
        )

        # 2. Creer le gain revendeur
        try:
            payload_gain = {
                "revendeur_id": revendeur_id,
                "montant": montant_net,
                "montant_brut": total,
                "commission": commission,
                "commission_pct": commission_pct,
                "source_type": "commande_boutique",
                "source_id": str(commande.get("id")),
            }
            requests.post(_url("revendeur_gains"), json=payload_gain,
                         headers=_headers(True), timeout=10)
        except Exception as e:
            logger.error(f"appliquer_commission create_gain: {type(e).__name__}")

        # 3. Mettre a jour la commande
        update_commande_boutique(commande["id"], {
            "commission_appliquee": True,
            "commission_montant": commission,
        })

        # 4. Verifier si credit < seuil de pause (500 F)
        boutique_desactivee = False
        profil_maj = get_profile(revendeur_id)
        if profil_maj:
            credit_actuel = float(profil_maj.get("credit_boost", 0) or 0)
            if credit_actuel < SEUIL_CREDIT_PAUSE:
                update_profile(revendeur_id, {"boutique_active": False})
                boutique_desactivee = True

        return {
            "succes": True,
            "commission": commission,
            "montant_net": montant_net,
            "nouveau_credit_boost": nouveau_credit,
            "boutique_desactivee": boutique_desactivee,
        }
    except Exception as e:
        logger.error(f"appliquer_commission_commande: {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# SERVICES (Digital)
# ═══════════════════════════════════════════════════════════════

def get_active_services(network=None):
    try:
        if network:
            url = _url(f"services?actif=eq.true&reseau=eq.{network}&order=categorie")
        else:
            url = _url("services?actif=eq.true&order=reseau,categorie")
        r = requests.get(url, headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_active_services: {type(e).__name__}")
        return []


def get_service_by_id(service_id):
    try:
        r = requests.get(_url(f"services?id=eq.{service_id}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_service_by_id: {type(e).__name__}")
        return None


def get_revendeur_prix_all(revendeur_id):
    try:
        r = requests.get(_url(f"revendeur_prix?revendeur_id=eq.{revendeur_id}"), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_revendeur_prix_all: {type(e).__name__}")
        return []


def get_revendeur_prix(revendeur_id, service_id):
    try:
        r = requests.get(
            _url(f"revendeur_prix?revendeur_id=eq.{revendeur_id}&service_id=eq.{service_id}&limit=1"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_revendeur_prix: {type(e).__name__}")
        return None


def set_revendeur_prix(revendeur_id, service_id, prix_fcfa):
    existing = get_revendeur_prix(revendeur_id, service_id)
    try:
        if existing:
            r = requests.patch(
                _url(f"revendeur_prix?id=eq.{existing['id']}"),
                json={"prix_fcfa": prix_fcfa},
                headers=_headers(True), timeout=10
            )
        else:
            r = requests.post(
                _url("revendeur_prix"),
                json={"revendeur_id": revendeur_id, "service_id": service_id, "prix_fcfa": prix_fcfa},
                headers=_headers(True), timeout=10
            )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"set_revendeur_prix: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# PRODUITS BOUTIQUE
# ═══════════════════════════════════════════════════════════════

def get_produits_revendeur(revendeur_id, only_active=False):
    try:
        url = f"boutique_produits?revendeur_id=eq.{revendeur_id}&order=ordre,created_at.desc"
        if only_active:
            url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_produits_revendeur: {type(e).__name__}")
        return []


def get_produit_boutique(produit_id):
    try:
        r = requests.get(_url(f"boutique_produits?id=eq.{produit_id}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_produit_boutique: {type(e).__name__}")
        return None


def create_produit_boutique(data):
    try:
        r = requests.post(_url("boutique_produits"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_produit_boutique: {type(e).__name__}")
        return None


def update_produit_boutique(produit_id, data):
    try:
        r = requests.patch(
            _url(f"boutique_produits?id=eq.{produit_id}"),
            json=data,
            headers=_headers(True), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_produit_boutique: {type(e).__name__}")
        return False


def delete_produit_boutique(produit_id):
    try:
        r = requests.delete(_url(f"boutique_produits?id=eq.{produit_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"delete_produit_boutique: {type(e).__name__}")
        return False


def get_produit_by_id(produit_id):
    return get_produit_boutique(produit_id)


def decrementer_stock(produit_id, quantite):
    try:
        produit = get_produit_by_id(produit_id)
        if not produit:
            return False
        stock_actuel = produit.get("stock", -1)
        if stock_actuel is None or stock_actuel < 0:
            return True
        nouveau_stock = max(0, stock_actuel - quantite)
        return update_produit_boutique(produit_id, {"stock": nouveau_stock})
    except Exception as e:
        logger.error(f"decrementer_stock: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# COMMANDES BOUTIQUE
# ═══════════════════════════════════════════════════════════════

def create_commande_boutique(data):
    try:
        r = requests.post(_url("boutique_commandes"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_commande_boutique: {type(e).__name__}")
        return None


def get_commande_boutique_by_reference(reference):
    try:
        r = requests.get(
            _url(f"boutique_commandes?reference=eq.{reference}&limit=1"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_commande_boutique_by_reference: {type(e).__name__}")
        return None


def get_commandes_boutique_revendeur(revendeur_id, limit=100, statut=None):
    try:
        url = f"boutique_commandes?revendeur_id=eq.{revendeur_id}&order=created_at.desc&limit={limit}"
        if statut:
            url += f"&statut=eq.{statut}"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_commandes_boutique_revendeur: {type(e).__name__}")
        return []


def update_commande_boutique(commande_id, data):
    try:
        r = requests.patch(_url(f"boutique_commandes?id=eq.{commande_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_commande_boutique: {type(e).__name__}")
        return False