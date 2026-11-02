"""
Fonctions Supabase pour Boost Reseller.
Inclut TOUTES les fonctions (profils, produits, commandes, wallet, retraits, avis, coupons...).
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
# PAYS DU REVENDEUR
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
        return profile.get("pays_code") if profile else None
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
        r = requests.get(_url(f"abonnements_plans?code=eq.{code}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_plan_by_code: {type(e).__name__}")
        return None

def get_plan_actuel(profile):
    code = (profile or {}).get("abonnement_niveau") or "gratuit"
    return get_plan_by_code(code) or get_plan_by_code("gratuit")

def get_commission_pct(profile):
    if profile and profile.get("revendeur_commission_pct") is not None:
        return float(profile["revendeur_commission_pct"])
    plan = get_plan_actuel(profile)
    return float((plan or {}).get("commission_pct", 0.10))

# ═══════════════════════════════════════════════════════════════
# LIMITES PAR PLAN
# ═══════════════════════════════════════════════════════════════

def peut_creer_produit(profile):
    plan = get_plan_actuel(profile)
    if not plan: return True, None
    max_p = plan.get("max_produits", 5)
    if max_p >= 999999: return True, None
    if len(get_produits_revendeur(profile["id"])) >= max_p:
        return False, f"Limite atteinte : {max_p} produits max."
    return True, None

def peut_creer_banniere(profile):
    plan = get_plan_actuel(profile)
    if not plan: return True, None
    max_b = plan.get("max_bannieres", 2)
    if max_b >= 999999: return True, None
    if len(get_bannieres_revendeur(profile["id"])) >= max_b:
        return False, f"Limite atteinte : {max_b} bannieres max."
    return True, None

def peut_creer_attribut(profile):
    plan = get_plan_actuel(profile)
    if not plan: return True, None
    max_a = plan.get("max_attributs", 2)
    if max_a >= 999999: return True, None
    if len(get_attributs_revendeur(profile["id"])) >= max_a:
        return False, f"Limite atteinte : {max_a} attributs max."
    return True, None

def peut_creer_coupon(profile):
    plan = get_plan_actuel(profile)
    if not plan: return True, None
    max_c = plan.get("max_coupons", 0)
    if max_c >= 999999: return True, None
    if len(get_coupons_revendeur(profile["id"])) >= max_c:
        return False, "Limite atteinte."
    return True, None

# ═══════════════════════════════════════════════════════════════
# CRÉDIT BOOST & WALLET
# ═══════════════════════════════════════════════════════════════

def get_credit_boost(user_id):
    try:
        profile = get_profile(user_id)
        return float(profile.get("credit_boost", 0) or 0) if profile else 0
    except Exception:
        return 0

def get_solde_wallet(user_id):
    try:
        profile = get_profile(user_id)
        return float(profile.get("solde_wallet", 0) or 0) if profile else 0
    except Exception:
        return 0

def credit_boost_suffisant(profile):
    return bool(profile and float(profile.get("credit_boost", 0) or 0) >= SEUIL_CREDIT_MIN_PUBLICATION)

def _log_credit_boost_transaction(revendeur_id, type_tx, montant, solde_apres, description=None, source_type=None, source_id=None, metadata=None):
    try:
        requests.post(_url("credit_boost_transactions"), json={
            "revendeur_id": revendeur_id, "type": type_tx, "montant": montant,
            "solde_apres": solde_apres, "description": description,
            "source_type": source_type, "source_id": source_id, "metadata": metadata or {},
        }, headers=_headers(True), timeout=10)
    except Exception:
        pass

def debiter_credit_boost(user_id, montant, description=None, source_type=None, source_id=None, metadata=None):
    try:
        profile = get_profile(user_id)
        if not profile: return None
        nouveau_solde = float(profile.get("credit_boost", 0) or 0) - float(montant)
        if update_profile(user_id, {"credit_boost": nouveau_solde}):
            _log_credit_boost_transaction(user_id, "debit_commission", -abs(float(montant)), nouveau_solde, description, source_type, source_id, metadata)
            return nouveau_solde
        return None
    except Exception:
        return None

def crediter_credit_boost(user_id, montant, description=None, source_type=None, source_id=None, metadata=None):
    try:
        profile = get_profile(user_id)
        if not profile: return None
        nouveau_solde = float(profile.get("credit_boost", 0) or 0) + float(montant)
        if update_profile(user_id, {"credit_boost": nouveau_solde}):
            _log_credit_boost_transaction(user_id, "recharge", float(montant), nouveau_solde, description, source_type, source_id, metadata)
            reactiver_boutique_si_solde_ok(user_id)
            return nouveau_solde
        return None
    except Exception:
        return None

def reactiver_boutique_si_solde_ok(user_id):
    try:
        profile = get_profile(user_id)
        if profile and profile.get("est_revendeur") and not profile.get("boutique_active"):
            if float(profile.get("credit_boost", 0) or 0) >= SEUIL_CREDIT_PAUSE:
                update_profile(user_id, {"boutique_active": True})
                return True
        return False
    except Exception:
        return False

def get_transactions_credit_boost(user_id, limit=100):
    try:
        r = requests.get(_url(f"credit_boost_transactions?revendeur_id=eq.{user_id}&order=created_at.desc&limit={limit}"), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

# ═══════════════════════════════════════════════════════════════
# RETRAITS
# ═══════════════════════════════════════════════════════════════

def create_demande_retrait(data):
    try:
        r = requests.post(_url("demandes_retrait"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception:
        return None

def get_demande_retrait(demande_id):
    try:
        r = requests.get(_url(f"demandes_retrait?id=eq.{demande_id}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None

def get_demandes_retrait_par_revendeur(revendeur_id):
    try:
        r = requests.get(_url(f"demandes_retrait?revendeur_id=eq.{revendeur_id}&order=created_at.desc"), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def update_demande_retrait(demande_id, data):
    try:
        r = requests.patch(_url(f"demandes_retrait?id=eq.{demande_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# COMMISSION
# ═══════════════════════════════════════════════════════════════

def appliquer_commission_commande(commande, profile=None):
    try:
        if not commande or commande.get("commission_appliquee"): return {"succes": True}
        revendeur_id = commande.get("revendeur_id")
        if not revendeur_id: return None
        if not profile: profile = get_profile(revendeur_id)
        if not profile: return None

        total = float(commande.get("total", 0) or 0)
        if total <= 0: return None

        commission_pct = float(profile.get("revendeur_commission_pct", 0.10) or 0.10)
        commission = round(total * commission_pct, 2)
        montant_net = round(total - commission, 2)

        debiter_credit_boost(revendeur_id, commission, description=f"Commission commande {commande.get('reference')}", source_type="commande_boutique", source_id=str(commande.get("id")))
        
        try:
            requests.post(_url("revendeur_gains"), json={
                "revendeur_id": revendeur_id, "montant": montant_net, "montant_brut": total,
                "commission": commission, "commission_pct": commission_pct,
                "source_type": "commande_boutique", "source_id": str(commande.get("id")),
            }, headers=_headers(True), timeout=10)
        except Exception:
            pass

        update_commande_boutique(commande["id"], {"commission_appliquee": True, "commission_montant": commission})

        boutique_desactivee = False
        profil_maj = get_profile(revendeur_id)
        if profil_maj and float(profil_maj.get("credit_boost", 0) or 0) < SEUIL_CREDIT_PAUSE:
            update_profile(revendeur_id, {"boutique_active": False})
            boutique_desactivee = True

        return {"succes": True, "commission": commission, "montant_net": montant_net, "boutique_desactivee": boutique_desactivee}
    except Exception as e:
        logger.error(f"appliquer_commission_commande: {type(e).__name__}")
        return None

# ═══════════════════════════════════════════════════════════════
# BOUTIQUE TYPES / CATEGORIES / SERVICES
# ═══════════════════════════════════════════════════════════════

def get_all_boutique_types(only_active=True):
    try:
        url = "boutique_types?order=ordre"
        if only_active: url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def get_boutique_type(code):
    try:
        r = requests.get(_url(f"boutique_types?code=eq.{code}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None

def get_categories_par_type(type_code):
    try:
        r = requests.get(_url(f"boutique_categories?type_code=eq.{type_code}&actif=eq.true&order=ordre"), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def create_categorie(type_code, nom, description=None):
    try:
        r = requests.post(_url("boutique_categories"), json={"type_code": type_code, "nom": nom, "description": description, "actif": True}, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception:
        return None

def update_categorie(cat_id, data):
    try:
        r = requests.patch(_url(f"boutique_categories?id=eq.{cat_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

def delete_categorie(cat_id):
    try:
        r = requests.delete(_url(f"boutique_categories?id=eq.{cat_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

def get_active_services(network=None):
    try:
        url = _url(f"services?actif=eq.true&reseau=eq.{network}&order=categorie") if network else _url("services?actif=eq.true&order=reseau,categorie")
        r = requests.get(url, headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def get_service_by_id(service_id):
    try:
        r = requests.get(_url(f"services?id=eq.{service_id}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════
# PRIX
# ═══════════════════════════════════════════════════════════════

def get_revendeur_prix_all(revendeur_id):
    try:
        r = requests.get(_url(f"revendeur_prix?revendeur_id=eq.{revendeur_id}"), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def get_revendeur_prix(revendeur_id, service_id):
    try:
        r = requests.get(_url(f"revendeur_prix?revendeur_id=eq.{revendeur_id}&service_id=eq.{service_id}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None

def set_revendeur_prix(revendeur_id, service_id, prix_fcfa):
    existing = get_revendeur_prix(revendeur_id, service_id)
    try:
        if existing:
            r = requests.patch(_url(f"revendeur_prix?id=eq.{existing['id']}"), json={"prix_fcfa": prix_fcfa}, headers=_headers(True), timeout=10)
        else:
            r = requests.post(_url("revendeur_prix"), json={"revendeur_id": revendeur_id, "service_id": service_id, "prix_fcfa": prix_fcfa}, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# PRODUITS
# ═══════════════════════════════════════════════════════════════

def get_produits_revendeur(revendeur_id, only_active=False):
    try:
        url = f"boutique_produits?revendeur_id=eq.{revendeur_id}&order=ordre,created_at.desc"
        if only_active: url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def get_produit_boutique(produit_id):
    try:
        r = requests.get(_url(f"boutique_produits?id=eq.{produit_id}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None

def create_produit_boutique(data):
    try:
        r = requests.post(_url("boutique_produits"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception:
        return None

def update_produit_boutique(produit_id, data):
    try:
        r = requests.patch(_url(f"boutique_produits?id=eq.{produit_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

def delete_produit_boutique(produit_id):
    try:
        r = requests.delete(_url(f"boutique_produits?id=eq.{produit_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

def get_produit_by_id(produit_id):
    return get_produit_boutique(produit_id)

def decrementer_stock(produit_id, quantite):
    try:
        produit = get_produit_by_id(produit_id)
        if not produit: return False
        stock = produit.get("stock", -1)
        if stock is None or stock < 0: return True
        return update_produit_boutique(produit_id, {"stock": max(0, stock - quantite)})
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# BANNIERES
# ═══════════════════════════════════════════════════════════════

def get_bannieres_revendeur(revendeur_id, only_active=False):
    try:
        url = f"boutique_bannieres?revendeur_id=eq.{revendeur_id}&order=ordre,created_at.desc"
        if only_active: url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def create_banniere(data):
    try:
        r = requests.post(_url("boutique_bannieres"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception:
        return None

def update_banniere(banniere_id, data):
    try:
        r = requests.patch(_url(f"boutique_bannieres?id=eq.{banniere_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

def delete_banniere(banniere_id):
    try:
        r = requests.delete(_url(f"boutique_bannieres?id=eq.{banniere_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# ATTRIBUTS
# ═══════════════════════════════════════════════════════════════

def get_attributs_revendeur(revendeur_id, only_active=False):
    try:
        url = f"boutique_attributs?revendeur_id=eq.{revendeur_id}&order=ordre,created_at"
        if only_active: url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def create_attribut(data):
    try:
        r = requests.post(_url("boutique_attributs"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception:
        return None

def update_attribut(attribut_id, data):
    try:
        r = requests.patch(_url(f"boutique_attributs?id=eq.{attribut_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

def delete_attribut(attribut_id):
    try:
        r = requests.delete(_url(f"boutique_attributs?id=eq.{attribut_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# AVIS
# ═══════════════════════════════════════════════════════════════

def get_avis_revendeur(revendeur_id, only_approuve=False):
    try:
        url = f"boutique_avis?revendeur_id=eq.{revendeur_id}&order=created_at.desc"
        if only_approuve: url += "&approuve=eq.true"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def create_avis(data):
    try:
        r = requests.post(_url("boutique_avis"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception:
        return None

def update_avis(avis_id, data):
    try:
        r = requests.patch(_url(f"boutique_avis?id=eq.{avis_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

def delete_avis(avis_id):
    try:
        r = requests.delete(_url(f"boutique_avis?id=eq.{avis_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# COUPONS
# ═══════════════════════════════════════════════════════════════

def get_coupons_revendeur(revendeur_id):
    try:
        r = requests.get(_url(f"boutique_coupons?revendeur_id=eq.{revendeur_id}&order=created_at.desc"), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def get_coupon_by_code(revendeur_id, code):
    try:
        r = requests.get(_url(f"boutique_coupons?revendeur_id=eq.{revendeur_id}&code=eq.{code}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None

def create_coupon(data):
    try:
        r = requests.post(_url("boutique_coupons"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception:
        return None

def update_coupon(coupon_id, data):
    try:
        r = requests.patch(_url(f"boutique_coupons?id=eq.{coupon_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

def delete_coupon(coupon_id):
    try:
        r = requests.delete(_url(f"boutique_coupons?id=eq.{coupon_id}"), headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# COMMANDES
# ═══════════════════════════════════════════════════════════════

def create_commande_boutique(data):
    try:
        r = requests.post(_url("boutique_commandes"), json=data, headers=_headers(True), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception:
        return None

def get_commande_boutique_by_reference(reference):
    try:
        r = requests.get(_url(f"boutique_commandes?reference=eq.{reference}&limit=1"), headers=_headers(True), timeout=10)
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception:
        return None

def get_commandes_boutique_revendeur(revendeur_id, limit=100, statut=None):
    try:
        url = f"boutique_commandes?revendeur_id=eq.{revendeur_id}&order=created_at.desc&limit={limit}"
        if statut: url += f"&statut=eq.{statut}"
        r = requests.get(_url(url), headers=_headers(True), timeout=10)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []

def update_commande_boutique(commande_id, data):
    try:
        r = requests.patch(_url(f"boutique_commandes?id=eq.{commande_id}"), json=data, headers=_headers(True), timeout=10)
        return r.status_code < 300
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════
# CLIENTS & ORDERS DIVERS
# ═══════════════════════════════════════════════════════════════

def get_revendeur_clients_detail(revendeur_id):
    try:
        r = requests.get(_url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}&order=created_at.desc"), headers=_headers(True), timeout=10)
        liens = r.json()
        if not isinstance(liens, list): return []
        resultat = []
        for l in liens:
            profil = get_profile(l.get("client_id"))
            if profil:
                resultat.append({"id": profil.get("id"), "email": profil.get("email"), "full_name": profil.get("full_name"), "balance": profil.get("balance", 0), "country": profil.get("country"), "rattache_le": l.get("created_at")})
        return resultat
    except Exception:
        return []

def get_revendeur_orders(revendeur_id, limit=100):
    try:
        r = requests.get(_url(f"revendeur_clients?revendeur_id=eq.{revendeur_id}&select=client_id"), headers=_headers(True), timeout=10)
        liens = r.json()
        client_ids = [l.get("client_id") for l in liens] if isinstance(liens, list) else []
        if not client_ids: return []
        ids_str = ",".join(client_ids)
        r2 = requests.get(_url(f"commandes?user_id=in.({ids_str})&order=created_at.desc&limit={limit}"), headers=_headers(True), timeout=10)
        return r2.json() if r2.status_code == 200 else []
    except Exception:
        return []