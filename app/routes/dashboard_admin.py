"""
Dashboard admin — Gestion des fonctionnalités de la plateforme.
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app import limiter
from app.models.security import login_required
from app.models.database import get_profile, get_all_revendeurs, update_profile
from app.models.fonctionnalites import (
    get_toutes_fonctionnalites, toggle_fonctionnalite,
    toggle_premium_fonctionnalite, activer_feature_revendeur,
    get_features_revendeur
)

logger = logging.getLogger(__name__)
dashboard_admin_bp = Blueprint("dashboard_admin", __name__)


def _require_admin():
    """Verifie que l'utilisateur connecte est admin."""
    user_id = session.get("user_id")
    if not user_id:
        return None, redirect(url_for("auth.connexion"))
    profile = get_profile(user_id)
    if not profile:
        from app.models.security import clear_session
        clear_session()
        return None, redirect(url_for("auth.connexion"))
    if not profile.get("est_admin"):
        flash("Acces reserve aux administrateurs.", "error")
        return None, redirect(url_for("dashboard.index"))
    return profile, None


@dashboard_admin_bp.route("/")
@login_required
def index():
    """Liste des fonctionnalites dev."""
    profile, redir = _require_admin()
    if redir:
        return redir

    features = get_toutes_fonctionnalites()
    return render_template("dashboard/admin/fonctionnalites.html",
                          profile=profile,
                          features=features)


@dashboard_admin_bp.route("/fonctionnalites/<code>/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def fonctionnalite_toggle(code):
    profile, redir = _require_admin()
    if redir:
        return redir

    actif = request.form.get("actif") == "1"
    ok = toggle_fonctionnalite(code, not actif)

    if ok:
        flash(f"Fonctionnalite '{code}' {'desactivee' if actif else 'activee'}.", "success")
    else:
        flash("Erreur lors du changement.", "error")
    return redirect(url_for("dashboard_admin.index"))


@dashboard_admin_bp.route("/fonctionnalites/<code>/premium", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def fonctionnalite_premium(code):
    profile, redir = _require_admin()
    if redir:
        return redir

    est_premium = request.form.get("est_premium") == "1"
    ok = toggle_premium_fonctionnalite(code, not est_premium)

    if ok:
        flash(f"Fonctionnalite '{code}' marquee comme {'gratuite' if est_premium else 'premium'}.", "success")
    else:
        flash("Erreur lors du changement.", "error")
    return redirect(url_for("dashboard_admin.index"))


@dashboard_admin_bp.route("/revendeurs")
@login_required
def revendeurs():
    """Liste des revendeurs pour gerer leurs features."""
    profile, redir = _require_admin()
    if redir:
        return redir

    revendeurs = get_all_revendeurs(limit=200)
    return render_template("dashboard/admin/revendeurs.html",
                          profile=profile,
                          revendeurs=revendeurs)


@dashboard_admin_bp.route("/revendeurs/<revendeur_id>/features")
@login_required
def revendeur_features(revendeur_id):
    """Detail des features d'un revendeur."""
    profile, redir = _require_admin()
    if redir:
        return redir

    revendeur = get_profile(revendeur_id)
    if not revendeur:
        flash("Revendeur introuvable.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    toutes_features = get_toutes_fonctionnalites()
    features_actives = {f["feature_code"]: f.get("actif", False) for f in get_features_revendeur(revendeur_id)}

    return render_template("dashboard/admin/revendeur_features.html",
                          profile=profile,
                          revendeur=revendeur,
                          features=toutes_features,
                          features_actives=features_actives)


@dashboard_admin_bp.route("/revendeurs/<revendeur_id>/features/<code>/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def revendeur_feature_toggle(revendeur_id, code):
    profile, redir = _require_admin()
    if redir:
        return redir

    actif_actuel = request.form.get("actif") == "1"
    ok = activer_feature_revendeur(revendeur_id, code, not actif_actuel)

    if ok:
        flash(f"Feature '{code}' {'desactivee' if actif_actuel else 'activee'} pour ce revendeur.", "success")
    else:
        flash("Erreur lors du changement.", "error")
    return redirect(url_for("dashboard_admin.revendeur_features", revendeur_id=revendeur_id))