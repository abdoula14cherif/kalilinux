"""
Fonctions Supabase pour le site reseller.
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
    La commission est lue dynamiquement depuis le plan (get_commission_pct),
    donc plus besoin de la passer en dur.
    """
    try:
        # Récupère la commission du plan actuel pour la stocker (denormalisation)
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

def _compter_usage(profile):
    """Compte l'usage actuel du revendeur pour les limites."""
    return {
        "produits": len(get_produits_revendeur(profile["id"])),
        "bannieres": len(get_bannieres_revendeur(profile["id"])),
        "attributs": len(get_attributs_revendeur(profile["id"])),
        "coupons": len(get_coupons_revendeur(profile["id"])),
    }


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
    montant_brut  = total paye par le client
    montant_net   = ce que le revendeur recoit reellement
    commission_pct = taux preleve par la plateforme (ex: 0.10)
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