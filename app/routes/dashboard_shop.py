"""
Dashboard revendeur — routes secondaires (commandes, coupons, avis, contacts, gains, abonnement).
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app import limiter
from app.models.security import login_required
from app.models.database import (
    get_profile, update_profile,
    get_revendeur_clients_detail, get_revendeur_orders,
    get_revendeur_gains_total,
    get_produits_revendeur, get_categories_par_type,
    get_bannieres_revendeur, get_attributs_revendeur,
    get_avis_revendeur, create_avis, update_avis, delete_avis,
    get_coupons_revendeur, get_coupon_by_code, create_coupon, update_coupon, delete_coupon,
    get_commandes_boutique_revendeur, update_commande_boutique,
    get_abonnements_plans, get_fonctionnalites_premium,
    get_all_boutique_types
)

logger = logging.getLogger(__name__)
dashboard_shop_bp = Blueprint("dashboard_shop", __name__)


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


@dashboard_shop_bp.route("/commandes")
@login_required
def commandes():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    commandes_boutique = []
    try:
        commandes_boutique = get_commandes_boutique_revendeur(profile["id"], limit=200)
    except Exception as e:
        logger.error(f"commandes boutique load: {type(e).__name__}")

    orders_services = []
    try:
        orders_services = get_revendeur_orders(profile["id"], limit=200)
    except Exception as e:
        logger.error(f"commandes services load: {type(e).__name__}")

    return render_template("dashboard/commandes.html",
                          profile=profile,
                          commandes_boutique=commandes_boutique,
                          orders=orders_services)


@dashboard_shop_bp.route("/commande-boutique/statut", methods=["POST"])
@login_required
@limiter.limit("120 per hour")
def commande_boutique_statut():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    commande_id = request.form.get("commande_id", "")
    statut = request.form.get("statut", "")

    if not commande_id or statut not in ("en_attente", "confirmee", "en_livraison", "livree", "annulee"):
        flash("Donnees invalides.", "error")
        return redirect(url_for("dashboard_shop.commandes"))

    if not _verifier_propriete("boutique_commandes", commande_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative modif commande {commande_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard_shop.commandes"))

    ok = update_commande_boutique(commande_id, {"statut": statut})

    if ok:
        labels = {
            "en_attente": "en attente",
            "confirmee": "confirmee",
            "en_livraison": "en livraison",
            "livree": "livree",
            "annulee": "annulee"
        }
        flash(f"Commande mise a jour : {labels.get(statut, statut)}.", "success")
    else:
        flash("Erreur lors de la mise a jour.", "error")

    return redirect(url_for("dashboard_shop.commandes"))


@dashboard_shop_bp.route("/gains")
@login_required
def gains():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    gains_total = 0
    try:
        gains_total = get_revendeur_gains_total(profile["id"])
    except Exception as e:
        logger.error(f"gains load: {type(e).__name__}")
    return render_template("dashboard/gains.html", profile=profile, gains_total=gains_total)


@dashboard_shop_bp.route("/contacts")
@login_required
def contacts():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    mes_contacts = []
    try:
        mes_contacts = get_revendeur_clients_detail(profile["id"])
    except Exception as e:
        logger.error(f"contacts load: {type(e).__name__}")
        flash("Impossible de charger vos contacts pour le moment.", "warning")
    return render_template("dashboard/contacts.html", profile=profile, contacts=mes_contacts)


@dashboard_shop_bp.route("/reviews")
@login_required
def reviews():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    liste = get_avis_revendeur(profile["id"])
    return render_template("dashboard/reviews.html", profile=profile, avis=liste)


@dashboard_shop_bp.route("/reviews/ajouter", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def reviews_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    client_nom = request.form.get("client_nom", "").strip()[:60]
    client_email = request.form.get("client_email", "").strip()[:150] or None
    commentaire = request.form.get("commentaire", "").strip()[:500] or None

    try:
        note = int(request.form.get("note", 5))
        note = max(1, min(5, note))
    except Exception:
        note = 5

    if not client_nom:
        flash("Le nom du client est obligatoire.", "error")
        return redirect(url_for("dashboard_shop.reviews"))

    result = create_avis({
        "revendeur_id": profile["id"],
        "client_nom": client_nom,
        "client_email": client_email,
        "note": note,
        "commentaire": commentaire,
        "approuve": True,
    })

    if result:
        flash(f"Avis de {client_nom} ajoute !", "success")
    else:
        flash("Erreur lors de l'ajout de l'avis.", "error")

    return redirect(url_for("dashboard_shop.reviews"))


@dashboard_shop_bp.route("/reviews/approuver", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def reviews_approuver():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    avis_id = request.form.get("avis_id", "")
    approuve = request.form.get("approuve") == "1"

    if not avis_id:
        flash("ID avis manquant.", "error")
        return redirect(url_for("dashboard_shop.reviews"))

    if not _verifier_propriete("boutique_avis", avis_id, profile["id"]):
        flash("Action non autorisee.", "error")
        return redirect(url_for("dashboard_shop.reviews"))

    update_avis(avis_id, {"approuve": not approuve})
    flash(f"Avis {'masque' if approuve else 'approuve'}.", "success")
    return redirect(url_for("dashboard_shop.reviews"))


@dashboard_shop_bp.route("/reviews/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def reviews_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    avis_id = request.form.get("avis_id", "")
    if not avis_id:
        flash("ID avis manquant.", "error")
        return redirect(url_for("dashboard_shop.reviews"))

    if not _verifier_propriete("boutique_avis", avis_id, profile["id"]):
        flash("Action non autorisee.", "error")
        return redirect(url_for("dashboard_shop.reviews"))

    delete_avis(avis_id)
    flash("Avis supprime.", "success")
    return redirect(url_for("dashboard_shop.reviews"))