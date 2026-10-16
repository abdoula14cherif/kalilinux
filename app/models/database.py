"""
Fonctions Supabase pour le site reseller.
"""
import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# SEUILS CREDIT BOOST
# ═══════════════════════════════════════════════════════════════

# Seuil minimum pour publier une boutique (obligatoire au démarrage)
SEUIL_CREDIT_MIN_PUBLICATION = 2000

# Seuil d'alerte visuelle (boutique active mais on prévient)
SEUIL_CREDIT_ALERTE = 2000

# Seuil critique : en dessous, la boutique est automatiquement mise en pause
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
        logger.error(f"debit_balance: {type(e).__name__}")
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
        logger.error(f"credit_balance: {type(e).__name__}")
        return None


def slug_deja_pris(slug):
    try:
        r = requests.get(_url(f"profiles?revendeur_slug=eq.{slug}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return isinstance(data, list) and len(data) > 0
    except Exception as e:
        logger.error(f"slug_deja_pris: {type(e).__name__}")
        return True


def activer_revendeur(user_id, slug):
    """
    Active le statut revendeur.
    La commission est lue dynamiquement depuis le plan.
    """
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


def toggle_boutique_active(revendeur_id, active):
    try:
        r = requests.patch(
            _url(f"profiles?id=eq.{revendeur_id}"),
            json={"boutique_active": active},
            headers=_headers(True), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_boutique_active: {type(e).__name__}")
        return False


def get_all_revendeurs(limit=200):
    try:
        r = requests.get(
            _url(f"profiles?est_revendeur=eq.true&order=created_at.desc&limit={limit}"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_all_revendeurs: {type(e).__name__}")
        return []


def incrementer_visite_boutique(revendeur_id):
    """Incremente atomiquement le compteur de visites via RPC Supabase."""
    try:
        r = requests.post(
            _url("rpc/incrementer_visite"),
            json={"revendeur_id": revendeur_id},
            headers=_headers(True),
            timeout=10
        )
        if r.status_code in (200, 201):
            try:
                return int(r.json())
            except Exception:
                return 1
        return 0
    except Exception as e:
        logger.error(f"incrementer_visite_boutique: {type(e).__name__}")
        return 0


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
    """Recupere un plan par son code (gratuit, pro, business)."""
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
    """Retourne le plan complet du revendeur (ou le plan gratuit par defaut)."""
    code = (profile or {}).get("abonnement_niveau") or "gratuit"
    plan = get_plan_by_code(code)
    if not plan:
        plan = get_plan_by_code("gratuit")
    return plan


def get_commission_pct(profile):
    """
    Retourne le pourcentage de commission que la plateforme preleve
    sur les ventes de ce revendeur (0.10 = 10%).
    """
    if profile and profile.get("revendeur_commission_pct") is not None:
        return float(profile["revendeur_commission_pct"])
    plan = get_plan_actuel(profile)
    return float((plan or {}).get("commission_pct", 0.10))


def get_fonctionnalites_premium():
    try:
        r = requests.get(_url("fonctionnalites_premium?actif=eq.true&order=ordre"), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_fonctionnalites_premium: {type(e).__name__}")
        return []


# ═══════════════════════════════════════════════════════════════
# LIMITES PAR PLAN
# ═══════════════════════════════════════════════════════════════

def peut_creer_produit(profile):
    """Retourne (True, None) si OK, sinon (False, message)."""
    plan = get_plan_actuel(profile)
    if not plan:
        return True, None
    max_p = plan.get("max_produits", 5)
    if max_p >= 999999:
        return True, None
    actuels = len(get_produits_revendeur(profile["id"]))
    if actuels >= max_p:
        return False, f"Limite atteinte : {max_p} produits max sur le plan {plan['nom']}. Passez au plan superieur."
    return True, None


def peut_creer_banniere(profile):
    plan = get_plan_actuel(profile)
    if not plan:
        return True, None
    max_b = plan.get("max_bannieres", 2)
    if max_b >= 999999:
        return True, None
    actuels = len(get_bannieres_revendeur(profile["id"]))
    if actuels >= max_b:
        return False, f"Limite atteinte : {max_b} bannieres max sur le plan {plan['nom']}."
    return True, None


def peut_creer_attribut(profile):
    plan = get_plan_actuel(profile)
    if not plan:
        return True, None
    max_a = plan.get("max_attributs", 2)
    if max_a >= 999999:
        return True, None
    actuels = len(get_attributs_revendeur(profile["id"]))
    if actuels >= max_a:
        return False, f"Limite atteinte : {max_a} attributs max sur le plan {plan['nom']}."
    return True, None


def peut_creer_coupon(profile):
    plan = get_plan_actuel(profile)
    if not plan:
        return True, None
    max_c = plan.get("max_coupons", 0)
    if max_c >= 999999:
        return True, None
    actuels = len(get_coupons_revendeur(profile["id"]))
    if actuels >= max_c:
        msg = f"Les coupons ne sont pas disponibles sur le plan {plan['nom']}." if max_c == 0 else f"Limite atteinte : {max_c} coupons max."
        return False, msg
    return True, None


# ═══════════════════════════════════════════════════════════════
# TYPES DE BOUTIQUES
# ═══════════════════════════════════════════════════════════════

def get_all_boutique_types(only_active=True):
    try:
        url = "boutique_types?order=ordre"
        if only_active:
            url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_all_boutique_types: {type(e).__name__}")
        return []


def get_boutique_type(code):
    try:
        r = requests.get(_url(f"boutique_types?code=eq.{code}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_boutique_type: {type(e).__name__}")
        return None


def get_categories_par_type(type_code):
    try:
        r = requests.get(
            _url(f"boutique_categories?type_code=eq.{type_code}&actif=eq.true&order=ordre"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_categories_par_type: {type(e).__name__}")
        return []


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
# CLIENTS REVENDEUR
# ═══════════════════════════════════════════════════════════════

def get_revendeur_clients(revendeur_id):
    try:
        r = requests.get(_url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}"), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_revendeur_clients: {type(e).__name__}")
        return []


def get_revendeur_clients_detail(revendeur_id):
    try:
        r = requests.get(
            _url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}&order=created_at.desc"),
            headers=_headers(True), timeout=10
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
        logger.error(f"get_revendeur_clients_detail: {type(e).__name__}")
        return []


def rattacher_client_revendeur(revendeur_id, client_id):
    try:
        exist = requests.get(
            _url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}&client_id=eq.{client_id}&limit=1"),
            headers=_headers(True), timeout=10
        ).json()
        if exist:
            return True
        r = requests.post(
            _url("revendeur_clients"),
            json={"revendeur_id": revendeur_id, "client_id": client_id},
            headers=_headers(True), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"rattacher_client_revendeur: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# COMMANDES REVENDEUR (services)
# ═══════════════════════════════════════════════════════════════

def get_revendeur_orders(revendeur_id, limit=100):
    try:
        r = requests.get(
            _url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}&select=client_id"),
            headers=_headers(True), timeout=10
        )
        liens = r.json()
        client_ids = [l.get("client_id") for l in liens] if isinstance(liens, list) else []
        if not client_ids:
            return []
        ids_str = ",".join(client_ids)
        r2 = requests.get(
            _url(f"commandes?user_id=in.({ids_str})&order=created_at.desc&limit={limit}"),
            headers=_headers(True), timeout=10
        )
        data = r2.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_revendeur_orders: {type(e).__name__}")
        return []


# ═══════════════════════════════════════════════════════════════
# GAINS REVENDEUR
# ═══════════════════════════════════════════════════════════════

def get_revendeur_gains_total(revendeur_id):
    try:
        r = requests.get(
            _url(f"revendeur_gains?revendeur_id=eq.{revendeur_id}&select=montant"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return sum(g.get("montant", 0) or 0 for g in data) if isinstance(data, list) else 0
    except Exception as e:
        logger.error(f"get_revendeur_gains_total: {type(e).__name__}")
        return 0


def create_revendeur_gain(revendeur_id, montant_brut, montant_net, commission_pct, source_type=None, source_id=None):
    """
    Enregistre un gain revendeur apres calcul de la commission plateforme.
    """
    try:
        commission = round(montant_brut * commission_pct, 2)
        payload = {
            "revendeur_id": revendeur_id,
            "montant": montant_net,
            "montant_brut": montant_brut,
            "commission": commission,
            "commission_pct": commission_pct,
            "source_type": source_type,
            "source_id": source_id,
        }
        r = requests.post(_url("revendeur_gains"), json=payload, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_revendeur_gain: {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# CRÉDIT BOOST (solde prépayé pour commissions)
# ═══════════════════════════════════════════════════════════════

def get_credit_boost(user_id):
    """Retourne le solde Credit Boost d'un revendeur."""
    try:
        profile = get_profile(user_id)
        if not profile:
            return 0
        return float(profile.get("credit_boost", 0) or 0)
    except Exception as e:
        logger.error(f"get_credit_boost: {type(e).__name__}")
        return 0


def credit_boost_suffisant(profile):
    """Verifie si le revendeur a assez de credit pour publier/continuer."""
    if not profile:
        return False
    return float(profile.get("credit_boost", 0) or 0) >= SEUIL_CREDIT_MIN_PUBLICATION


def _log_credit_boost_transaction(revendeur_id, type_tx, montant, solde_apres,
                                   description=None, source_type=None,
                                   source_id=None, metadata=None):
    """Enregistre une transaction dans l'historique."""
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
    """
    Debite le Credit Boost. Retourne le nouveau solde ou None si echec.
    """
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
    """Credite le Credit Boost (recharge). Retourne le nouveau solde."""
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
            # Reactiver la boutique si solde redevient ok
            reactiver_boutique_si_solde_ok(user_id)
            return nouveau_solde
        return None
    except Exception as e:
        logger.error(f"crediter_credit_boost: {type(e).__name__}")
        return None


def reactiver_boutique_si_solde_ok(user_id):
    """
    Reactive automatiquement la boutique si le credit est repasse
    au-dessus du seuil de pause (500 F).
    """
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
            logger.info(
                f"[REACTIVATION] Boutique {user_id} reactivee "
                f"(credit={credit_actuel} >= seuil={SEUIL_CREDIT_PAUSE})"
            )
            return True
        return False
    except Exception as e:
        logger.error(f"reactiver_boutique_si_solde_ok: {type(e).__name__}")
        return False


def get_transactions_credit_boost(user_id, limit=100):
    """Historique des transactions Credit Boost."""
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
# APPLICATION DE LA COMMISSION
# ═══════════════════════════════════════════════════════════════

def appliquer_commission_commande(commande, profile=None):
    """
    Applique la commission plateforme sur une commande.
    - Debite le credit_boost du revendeur
    - Cree un gain revendeur
    - Pour les ventes EN LIGNE : credite aussi le solde principal
    - Met la boutique en pause si credit < SEUIL_CREDIT_PAUSE (500 F)
    """
    try:
        if not commande:
            return None

        revendeur_id = commande.get("revendeur_id")
        if not revendeur_id:
            return None

        if commande.get("commission_appliquee"):
            logger.info(f"Commission deja appliquee pour commande {commande.get('reference')}")
            return {
                "succes": True,
                "deja_appliquee": True,
                "commission": float(commande.get("commission_montant", 0) or 0),
            }

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

        boutique_type = profile.get("boutique_type") or "general"
        type_obj = get_boutique_type(boutique_type) or {}
        paiement_type = type_obj.get("paiement_type", "cash")

        # 1. Debiter le credit_boost
        nouveau_credit = debiter_credit_boost(
            revendeur_id, commission,
            description=f"Commission commande {commande.get('reference')}",
            source_type="commande_boutique",
            source_id=str(commande.get("id")),
            metadata={
                "total": total,
                "commission_pct": commission_pct,
                "montant_net": montant_net,
                "paiement_type": paiement_type,
            }
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

        # 3. Si vente EN LIGNE : crediter le solde principal (net)
        if paiement_type == "en_ligne":
            credit_balance(revendeur_id, montant_net)

        # 4. Mettre a jour la commande
        update_commande_boutique(commande["id"], {
            "commission_appliquee": True,
            "commission_montant": commission,
        })

        # 5. Verifier si credit < seuil de pause (500 F) → desactiver boutique
        boutique_desactivee = False
        profil_maj = get_profile(revendeur_id)
        if profil_maj:
            credit_actuel = float(profil_maj.get("credit_boost", 0) or 0)
            if credit_actuel < SEUIL_CREDIT_PAUSE:
                update_profile(revendeur_id, {"boutique_active": False})
                boutique_desactivee = True
                logger.warning(
                    f"[COMMISSION] Boutique {revendeur_id} mise en pause "
                    f"(credit={credit_actuel} < seuil={SEUIL_CREDIT_PAUSE})"
                )

        return {
            "succes": True,
            "commission": commission,
            "montant_net": montant_net,
            "nouveau_credit_boost": nouveau_credit,
            "boutique_desactivee": boutique_desactivee,
            "paiement_type": paiement_type,
        }
    except Exception as e:
        logger.error(f"appliquer_commission_commande: {type(e).__name__}")
        return None


def rembourser_commission_commande(commande, profile=None):
    """Rembourse la commission (commande annulee apres application)."""
    try:
        if not commande or not commande.get("commission_appliquee"):
            return False
        revendeur_id = commande.get("revendeur_id")
        commission = float(commande.get("commission_montant", 0) or 0)
        if commission <= 0:
            return False

        crediter_credit_boost(
            revendeur_id, commission,
            description=f"Remboursement commande {commande.get('reference')}",
            source_type="remboursement",
            source_id=str(commande.get("id")),
        )

        if not profile:
            profile = get_profile(revendeur_id)
        if profile:
            boutique_type = profile.get("boutique_type") or "general"
            type_obj = get_boutique_type(boutique_type) or {}
            if type_obj.get("paiement_type") == "en_ligne":
                total = float(commande.get("total", 0) or 0)
                commission_pct = float(profile.get("revendeur_commission_pct", 0.10))
                net = round(total - (total * commission_pct), 2)
                debit_balance(revendeur_id, net)

        update_commande_boutique(commande["id"], {
            "commission_appliquee": False,
            "commission_montant": 0,
        })
        return True
    except Exception as e:
        logger.error(f"rembourser_commission_commande: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# CATEGORIES BOUTIQUE
# ═══════════════════════════════════════════════════════════════

def create_categorie(type_code, nom, description=None):
    try:
        r = requests.post(_url("boutique_categories"), json={
            "type_code": type_code,
            "nom": nom,
            "description": description,
            "actif": True,
        }, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_categorie: {type(e).__name__}")
        return None


def update_categorie(cat_id, data):
    try:
        r = requests.patch(_url(f"boutique_categories?id=eq.{cat_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_categorie: {type(e).__name__}")
        return False


def delete_categorie(cat_id):
    try:
        r = requests.delete(_url(f"boutique_categories?id=eq.{cat_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"delete_categorie: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# BANNIERES
# ═══════════════════════════════════════════════════════════════

def get_bannieres_revendeur(revendeur_id, only_active=False):
    try:
        url = f"boutique_bannieres?revendeur_id=eq.{revendeur_id}&order=ordre,created_at.desc"
        if only_active:
            url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_bannieres_revendeur: {type(e).__name__}")
        return []


def create_banniere(data):
    try:
        r = requests.post(_url("boutique_bannieres"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_banniere: {type(e).__name__}")
        return None


def update_banniere(banniere_id, data):
    try:
        r = requests.patch(_url(f"boutique_bannieres?id=eq.{banniere_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_banniere: {type(e).__name__}")
        return False


def delete_banniere(banniere_id):
    try:
        r = requests.delete(_url(f"boutique_bannieres?id=eq.{banniere_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"delete_banniere: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# ATTRIBUTS
# ═══════════════════════════════════════════════════════════════

def get_attributs_revendeur(revendeur_id, only_active=False):
    try:
        url = f"boutique_attributs?revendeur_id=eq.{revendeur_id}&order=ordre,created_at"
        if only_active:
            url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_attributs_revendeur: {type(e).__name__}")
        return []


def create_attribut(data):
    try:
        r = requests.post(_url("boutique_attributs"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_attribut: {type(e).__name__}")
        return None


def update_attribut(attribut_id, data):
    try:
        r = requests.patch(_url(f"boutique_attributs?id=eq.{attribut_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_attribut: {type(e).__name__}")
        return False


def delete_attribut(attribut_id):
    try:
        r = requests.delete(_url(f"boutique_attributs?id=eq.{attribut_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"delete_attribut: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# AVIS CLIENTS
# ═══════════════════════════════════════════════════════════════

def get_avis_revendeur(revendeur_id, only_approuve=False):
    try:
        url = f"boutique_avis?revendeur_id=eq.{revendeur_id}&order=created_at.desc"
        if only_approuve:
            url += "&approuve=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_avis_revendeur: {type(e).__name__}")
        return []


def create_avis(data):
    try:
        r = requests.post(_url("boutique_avis"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_avis: {type(e).__name__}")
        return None


def update_avis(avis_id, data):
    try:
        r = requests.patch(_url(f"boutique_avis?id=eq.{avis_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_avis: {type(e).__name__}")
        return False


def delete_avis(avis_id):
    try:
        r = requests.delete(_url(f"boutique_avis?id=eq.{avis_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"delete_avis: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# COUPONS
# ═══════════════════════════════════════════════════════════════

def get_coupons_revendeur(revendeur_id):
    try:
        r = requests.get(
            _url(f"boutique_coupons?revendeur_id=eq.{revendeur_id}&order=created_at.desc"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_coupons_revendeur: {type(e).__name__}")
        return []


def get_coupon_by_code(revendeur_id, code):
    try:
        r = requests.get(
            _url(f"boutique_coupons?revendeur_id=eq.{revendeur_id}&code=eq.{code}&limit=1"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_coupon_by_code: {type(e).__name__}")
        return None


def create_coupon(data):
    try:
        r = requests.post(_url("boutique_coupons"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"create_coupon: {type(e).__name__}")
        return None


def update_coupon(coupon_id, data):
    try:
        r = requests.patch(_url(f"boutique_coupons?id=eq.{coupon_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"update_coupon: {type(e).__name__}")
        return False


def delete_coupon(coupon_id):
    try:
        r = requests.delete(_url(f"boutique_coupons?id=eq.{coupon_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"delete_coupon: {type(e).__name__}")
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