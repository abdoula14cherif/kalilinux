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
    get_all_boutique_types, toggle_boutique_active,
    get_plan_by_code, get_plan_actuel, get_commission_pct,
    peut_creer_coupon,
    get_boutique_type,
    appliquer_commission_commande,
    rembourser_commission_commande,
    _url, _headers,
)
from app.models.serializers import avis_safe, coupon_safe, commande_safe

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


def _get_commande_by_id(commande_id):
    try:
        import requests
        r = requests.get(
            _url(f"boutique_commandes?id=eq.{commande_id}&limit=1"),
            headers=_headers(True), timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"_get_commande_by_id: {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# COMMANDES
# ═══════════════════════════════════════════════════════════════

@dashboard_shop_bp.route("/commandes")
@login_required
def commandes():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    commandes_boutique = []
    try:
        raw = get_commandes_boutique_revendeur(profile["id"], limit=200)
        commandes_boutique = [commande_safe(c) for c in raw]
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

    # Recuperer la commande AVANT modif (pour commission)
    commande = _get_commande_by_id(commande_id)
    if not commande:
        flash("Commande introuvable.", "error")
        return redirect(url_for("dashboard_shop.commandes"))

    # Mise a jour du statut
    ok = update_commande_boutique(commande_id, {"statut": statut})

    if not ok:
        flash("Erreur lors de la mise a jour.", "error")
        return redirect(url_for("dashboard_shop.commandes"))

    # ═══════════════════════════════════════════════════════════
    # APPLICATION / REMBOURSEMENT DE LA COMMISSION
    # ═══════════════════════════════════════════════════════════

    boutique_type = profile.get("boutique_type") or "general"
    type_obj = get_boutique_type(boutique_type) or {}
    paiement_type = type_obj.get("paiement_type", "cash")

    # CAS 1 : commande CASH livree → appliquer commission
    if (statut == "livree"
        and paiement_type == "cash"
        and not commande.get("commission_appliquee")):
        commande["statut"] = "livree"
        result = appliquer_commission_commande(commande, profile)

        if result and result.get("succes"):
            flash(
                f"Commande livree ! Commission de {result['commission']:,.0f} FCFA deduite "
                f"de votre Credit Boost. Net : {result['montant_net']:,.0f} FCFA.",
                "success"
            )
            if result.get("boutique_desactivee"):
                flash(
                    "⚠️ Votre Credit Boost est epuise. Boutique automatiquement mise en pause. "
                    "Rechargez pour reactiver.",
                    "warning"
                )
        else:
            flash("Commande livree, mais erreur lors du calcul de la commission.", "warning")

    # CAS 2 : commande annulee apres avoir ete payee/livree → rembourser commission
    elif (statut == "annulee"
          and commande.get("commission_appliquee")):
        result = rembourser_commission_commande(commande, profile)
        if result:
            flash("Commande annulee. Commission remboursee sur votre Credit Boost.", "info")

    # Flash normal
    labels = {
        "en_attente": "en attente",
        "confirmee": "confirmee",
        "en_livraison": "en livraison",
        "livree": "livree",
        "annulee": "annulee"
    }
    if statut not in ("livree", "annulee"):
        flash(f"Commande mise a jour : {labels.get(statut, statut)}.", "success")

    return redirect(url_for("dashboard_shop.commandes"))


# ═══════════════════════════════════════════════════════════════
# GAINS
# ═══════════════════════════════════════════════════════════════

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

    plan_actuel = get_plan_actuel(profile)
    commission_pct = get_commission_pct(profile)

    return render_template("dashboard/gains.html",
                          profile=profile,
                          gains_total=gains_total,
                          plan_actuel=plan_actuel,
                          commission_pct=commission_pct)


# ═══════════════════════════════════════════════════════════════
# CONTACTS
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# AVIS
# ═══════════════════════════════════════════════════════════════

@dashboard_shop_bp.route("/reviews")
@login_required
def reviews():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    liste = get_avis_revendeur(profile["id"])
    return render_template("dashboard/reviews.html", profile=profile,
                          avis=[avis_safe(a) for a in liste])


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


# ═══════════════════════════════════════════════════════════════
# COUPONS
# ═══════════════════════════════════════════════════════════════

@dashboard_shop_bp.route("/coupons")
@login_required
def coupons():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    liste = get_coupons_revendeur(profile["id"])
    plan_actuel = get_plan_actuel(profile)
    return render_template("dashboard/coupons.html",
                          profile=profile,
                          coupons=[coupon_safe(c) for c in liste],
                          plan_actuel=plan_actuel)


@dashboard_shop_bp.route("/coupons/ajouter", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def coupons_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    ok_limit, msg_limit = peut_creer_coupon(profile)
    if not ok_limit:
        flash(msg_limit, "error")
        return redirect(url_for("dashboard_shop.coupons"))

    code = request.form.get("code", "").strip().upper()[:20]
    type_coupon = request.form.get("type", "pourcentage")
    date_expiration = request.form.get("date_expiration", "").strip()[:30] or None

    if type_coupon not in ("pourcentage", "montant"):
        type_coupon = "pourcentage"

    if not code:
        flash("Le code promo est obligatoire.", "error")
        return redirect(url_for("dashboard_shop.coupons"))

    try:
        valeur = float(request.form.get("valeur", 10))
        if valeur <= 0 or valeur > 100000000:
            raise ValueError
    except Exception:
        flash("La valeur de reduction est invalide.", "error")
        return redirect(url_for("dashboard_shop.coupons"))

    if type_coupon == "pourcentage" and valeur > 100:
        flash("Le pourcentage ne peut pas depasser 100%.", "error")
        return redirect(url_for("dashboard_shop.coupons"))

    try:
        montant_min = float(request.form.get("montant_min", 0))
        montant_min = max(0, min(100000000, montant_min))
    except Exception:
        montant_min = 0

    try:
        max_util = int(request.form.get("max_utilisations", 100))
        max_util = max(1, min(1000000, max_util))
    except Exception:
        max_util = 100

    existant = get_coupon_by_code(profile["id"], code)
    if existant:
        flash(f"Le code '{code}' existe deja. Choisissez un autre code.", "error")
        return redirect(url_for("dashboard_shop.coupons"))

    result = create_coupon({
        "revendeur_id": profile["id"],
        "code": code,
        "type": type_coupon,
        "valeur": valeur,
        "montant_min": montant_min,
        "max_utilisations": max_util,
        "date_expiration": date_expiration,
        "actif": True,
    })

    if result:
        flash(f"Coupon '{code}' cree avec succes !", "success")
    else:
        flash("Erreur lors de la creation du coupon.", "error")

    return redirect(url_for("dashboard_shop.coupons"))


@dashboard_shop_bp.route("/coupons/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def coupons_toggle():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    coupon_id = request.form.get("coupon_id", "")
    actif = request.form.get("actif") == "1"

    if not coupon_id:
        flash("ID coupon manquant.", "error")
        return redirect(url_for("dashboard_shop.coupons"))

    if not _verifier_propriete("boutique_coupons", coupon_id, profile["id"]):
        flash("Action non autorisee.", "error")
        return redirect(url_for("dashboard_shop.coupons"))

    update_coupon(coupon_id, {"actif": not actif})
    flash(f"Coupon {'desactive' if actif else 'active'}.", "success")
    return redirect(url_for("dashboard_shop.coupons"))


@dashboard_shop_bp.route("/coupons/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def coupons_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    coupon_id = request.form.get("coupon_id", "")
    if not coupon_id:
        flash("ID coupon manquant.", "error")
        return redirect(url_for("dashboard_shop.coupons"))

    if not _verifier_propriete("boutique_coupons", coupon_id, profile["id"]):
        flash("Action non autorisee.", "error")
        return redirect(url_for("dashboard_shop.coupons"))

    delete_coupon(coupon_id)
    flash("Coupon supprime.", "success")
    return redirect(url_for("dashboard_shop.coupons"))


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS PREFERENCES
# ═══════════════════════════════════════════════════════════════

@dashboard_shop_bp.route("/notifications-prefs", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour")
def notifications_prefs():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if request.method == "POST":
        data = {
            "notif_nouvelle_commande": request.form.get("notif_nouvelle_commande") == "on",
            "notif_paiement_recu": request.form.get("notif_paiement_recu") == "on",
            "notif_nouvel_avis": request.form.get("notif_nouvel_avis") == "on",
            "notif_nouveau_client": request.form.get("notif_nouveau_client") == "on",
            "notif_resume_quotidien": request.form.get("notif_resume_quotidien") == "on",
            "notif_stock_bas": request.form.get("notif_stock_bas") == "on",
            "notif_email": request.form.get("notif_email", "").strip()[:150] or None,
        }
        ok = update_profile(profile["id"], data)
        if ok:
            flash("Preferences de notifications mises a jour !", "success")
        else:
            flash("Erreur lors de la sauvegarde.", "error")
        return redirect(url_for("dashboard_shop.notifications_prefs"))

    return render_template("dashboard/notifications_prefs.html", profile=profile)


# ═══════════════════════════════════════════════════════════════
# PREMIUM
# ═══════════════════════════════════════════════════════════════

@dashboard_shop_bp.route("/premium")
@login_required
def premium():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    features = get_fonctionnalites_premium()
    return render_template("dashboard/premium.html", profile=profile, features=features)


# ═══════════════════════════════════════════════════════════════
# ABONNEMENT
# ═══════════════════════════════════════════════════════════════

@dashboard_shop_bp.route("/abonnement")
@login_required
def abonnement():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    plans = get_abonnements_plans()

    produits = get_produits_revendeur(profile["id"])
    categories = get_categories_par_type(profile["boutique_type"])
    bannieres = get_bannieres_revendeur(profile["id"])
    attributs = get_attributs_revendeur(profile["id"])
    coupons = get_coupons_revendeur(profile["id"])

    usage = {
        "produits": len(produits),
        "categories": len(categories),
        "bannieres": len(bannieres),
        "attributs": len(attributs),
        "coupons": len(coupons),
    }

    plan_actuel = get_plan_actuel(profile)
    commission_pct = get_commission_pct(profile)

    return render_template("dashboard/abonnement.html",
                          profile=profile,
                          plans=plans,
                          plan_actuel=plan_actuel,
                          commission_pct=commission_pct,
                          usage=usage)


@dashboard_shop_bp.route("/abonnement/choisir", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def abonnement_choisir():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    plan_code = request.form.get("plan_code", "").strip()[:30]
    if not plan_code:
        flash("Plan invalide.", "error")
        return redirect(url_for("dashboard_shop.abonnement"))

    plan = get_plan_by_code(plan_code)
    if not plan:
        flash("Plan introuvable.", "error")
        return redirect(url_for("dashboard_shop.abonnement"))

    prix = float(plan.get("prix_mensuel", 0) or 0)
    commission_pct = float(plan.get("commission_pct", 0.10))

    # ─── PLAN GRATUIT → switch direct ────────────────────────
    if prix <= 0:
        ok = update_profile(profile["id"], {
            "abonnement_niveau": plan_code,
            "revendeur_commission_pct": commission_pct,
        })
        if ok:
            flash(f"Vous etes maintenant sur le plan {plan['nom']} !", "success")
        else:
            flash("Erreur lors du changement.", "error")
        return redirect(url_for("dashboard_shop.abonnement"))

    # ─── PLAN PAYANT → creation du lien Mysoleas ─────────────
    try:
        from app.models.mysoleas import creer_lien_paiement
    except ImportError:
        flash(f"Le plan {plan['nom']} sera bientot disponible ! Contactez le support.", "info")
        return redirect(url_for("dashboard_shop.abonnement"))

    lien = creer_lien_paiement(
        amount=prix,
        currency="XAF",
        title=f"Abonnement {plan['nom']}",
        description=f"Abonnement mensuel Boost Reseller - Plan {plan['nom']}",
        provider=None,
        fee_bearer="CUSTOMER",
        max_usage=1,
        metadata={
            "type": "abonnement",
            "user_id": profile["id"],
            "plan_code": plan_code,
            "plan_nom": plan["nom"],
            "montant": prix,
            "commission_pct": commission_pct,
        },
    )

    if not lien or not lien.get("payment_url"):
        flash("Erreur creation du lien de paiement. Reessayez.", "error")
        return redirect(url_for("dashboard_shop.abonnement"))

    return redirect(lien["payment_url"])


# ═══════════════════════════════════════════════════════════════
# PARAMETRES
# ═══════════════════════════════════════════════════════════════

@dashboard_shop_bp.route("/parametres")
@login_required
def parametres():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    types_boutique = get_all_boutique_types()
    return render_template("dashboard/parametres.html",
                          profile=profile,
                          types_boutique=types_boutique)


@dashboard_shop_bp.route("/boutique/toggle-active", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def boutique_toggle_active():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if not profile.get("est_revendeur"):
        flash("Vous devez publier votre boutique avant de pouvoir la desactiver.", "info")
        return redirect(url_for("dashboard_shop.parametres"))

    actif = request.form.get("actif") == "1"
    nouveau_statut = not actif

    ok = toggle_boutique_active(profile["id"], nouveau_statut)

    if ok:
        if nouveau_statut:
            flash("Boutique activee avec succes ! Vos clients peuvent de nouveau commander.", "success")
        else:
            flash("Boutique desactivee. Vos clients verront une page 'Boutique indisponible'.", "warning")
    else:
        flash("Erreur lors du changement de statut.", "error")

    return redirect(url_for("dashboard_shop.parametres"))


# ═══════════════════════════════════════════════════════════════
# API NOTIFICATIONS COUNT
# ═══════════════════════════════════════════════════════════════

@dashboard_shop_bp.route("/api/notifications-count")
@login_required
@limiter.limit("120 per hour")
def api_notifications_count():
    from flask import jsonify
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return jsonify({"error": "unauthorized"}), 401

    try:
        commandes_raw = get_commandes_boutique_revendeur(profile["id"], limit=500)
        commandes_attente = sum(1 for c in commandes_raw if c.get("statut") == "en_attente")
    except Exception as e:
        logger.error(f"api_notifications_count commandes: {type(e).__name__}")
        commandes_attente = 0

    try:
        avis_raw = get_avis_revendeur(profile["id"])
        avis_attente = sum(1 for a in avis_raw if not a.get("approuve"))
    except Exception as e:
        logger.error(f"api_notifications_count avis: {type(e).__name__}")
        avis_attente = 0

    return jsonify({
        "commandes_attente": commandes_attente,
        "avis_attente": avis_attente,
        "total": commandes_attente + avis_attente
    })