"""
Dashboard revendeur — toutes les pages de l'espace revendeur.
"""
import logging
import re
import json
from datetime import datetime, timezone
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, current_app
from app import limiter
from app.models.security import login_required
from app.models.database import (
    get_profile, update_profile, get_active_services,
    get_revendeur_prix_all, set_revendeur_prix, get_service_by_id,
    get_revendeur_clients_detail, get_revendeur_orders,
    get_revendeur_gains_total, slug_deja_pris,
    debit_balance, credit_balance, activer_revendeur,
    get_all_boutique_types, get_boutique_type, get_categories_par_type,
    get_produits_revendeur, create_produit_boutique, update_produit_boutique,
    delete_produit_boutique, get_produit_boutique,
    create_categorie, update_categorie, delete_categorie,
    get_bannieres_revendeur, create_banniere, update_banniere, delete_banniere,
    get_attributs_revendeur, create_attribut, update_attribut, delete_attribut,
    get_avis_revendeur, create_avis, update_avis, delete_avis,
    get_coupons_revendeur, get_coupon_by_code, create_coupon, update_coupon, delete_coupon,
    get_commandes_boutique_revendeur, update_commande_boutique,
    get_abonnements_plans, get_fonctionnalites_premium
)
from app.models.storage import upload_image

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)

THEMES = {
    "bleu":   ("#0066FF", "#0047CC"),
    "violet": ("#7C3AED", "#4C1D95"),
    "vert":   ("#059669", "#047857"),
    "orange": ("#F97316", "#EA580C"),
    "noir":   ("#0F172A", "#1E293B"),
    "rouge":  ("#DC2626", "#991B1B"),
}

PRIX_ACTIVATION = 5000


def _get_profile_ou_redirect(check_type=True):
    user_id = session.get("user_id")
    if not user_id:
        return None, redirect(url_for("auth.connexion"))
    profile = get_profile(user_id)
    if not profile:
        from app.models.security import clear_session
        clear_session()
        flash("Votre session a expire. Reconnectez-vous.", "warning")
        return None, redirect(url_for("auth.connexion"))

    if check_type and not profile.get("boutique_type"):
        if request.endpoint != "dashboard.choisir_type":
            flash("Choisissez d'abord un type de boutique pour continuer.", "info")
            return None, redirect(url_for("dashboard.choisir_type"))

    return profile, None


def _verifier_propriete(table, item_id, revendeur_id):
    try:
        if not item_id or not revendeur_id:
            return False
        from app.models.database import _url, _headers
        import requests
        r = requests.get(
            _url(f"{table}?id=eq.{item_id}&revendeur_id=eq.{revendeur_id}&limit=1"),
            headers=_headers(True),
            timeout=10
        )
        if r.status_code >= 300:
            return False
        data = r.json()
        return isinstance(data, list) and len(data) > 0
    except Exception as e:
        logger.error(f"_verifier_propriete {table}: {type(e).__name__}")
        return False


def _verifier_categorie_revendeur(cat_id, revendeur_id):
    try:
        if not cat_id or not revendeur_id:
            return False
        produits = get_produits_revendeur(revendeur_id)
        for p in produits:
            if str(p.get("categorie_id")) == str(cat_id):
                return True
        return False
    except Exception as e:
        logger.error(f"_verifier_categorie_revendeur: {type(e).__name__}")
        return False