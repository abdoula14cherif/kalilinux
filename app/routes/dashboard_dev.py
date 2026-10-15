"""
Dashboard développeur — Clés API, webhooks, documentation, playground.
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app import limiter
from app.models.security import login_required
from app.models.database import get_profile
from app.models.api_keys import (
    lister_cles, creer_cle, revoquer_cle, supprimer_cle
)
from app.models.fonctionnalites import (
    get_features_actives_pour_revendeur, revendeur_a_feature
)

logger = logging.getLogger(__name__)
dashboard_dev_bp = Blueprint("dashboard_dev", __name__)


def _get_profile_ou_redirect():
    user_id = session.get("user_id")
    if not user_id:
        return None, redirect(url_for("auth.connexion"))
    profile = get_profile(user_id)
    if not profile:
        from app.models.security import clear_session
        clear_session()
        flash("Votre session a expire. Reconnectez-vous.", "warning")
        return None, redirect(url_for("auth.connexion"))
    return profile, None


def _check_feature(profile, code):
    """Verifie si le revendeur a acces a la fonctionnalite. Sinon 403."""
    if not revendeur_a_feature(profile["id"], code, profile):
        flash("Cette fonctionnalite n'est pas activee sur votre compte.", "warning")
        return redirect(url_for("dashboard_dev.index"))
    return None


@dashboard_dev_bp.route("/")
@login_required
def index():
    """Hub développeur : liste des fonctionnalités disponibles."""
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    features = get_features_actives_pour_revendeur(profile["id"], profile)

    return render_template("dashboard/dev/index.html",
                          profile=profile,
                          features=features)


@dashboard_dev_bp.route("/api-keys")
@login_required
@limiter.limit("30 per hour")
def api_keys():
    """Liste des clés API du revendeur."""
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "api_keys")
    if redir_check:
        return redir_check

    cles = lister_cles(profile["id"])

    # On ajoute un flag pour savoir si la cle a ete utilisee recemment
    for c in cles:
        c["est_active"] = c.get("actif", True) and not c.get("revoked_at")

    return render_template("dashboard/dev/api_keys.html",
                          profile=profile,
                          cles=cles)


@dashboard_dev_bp.route("/api-keys/creer", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def api_keys_creer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "api_keys")
    if redir_check:
        return redir_check

    nom = request.form.get("nom", "").strip()[:60]
    if not nom:
        flash("Donnez un nom a votre cle API.", "error")
        return redirect(url_for("dashboard_dev.api_keys"))

    scopes = request.form.getlist("scopes")
    scopes_valides = {
        "boutique:read", "boutique:write",
        "produits:read", "produits:write",
        "commandes:read", "commandes:write",
        "clients:read",
        "stats:read",
    }
    scopes = [s for s in scopes if s in scopes_valides]
    if not scopes:
        scopes = ["boutique:read"]

    cle, full_key = creer_cle(profile["id"], nom, scopes)

    if not cle or not full_key:
        flash("Erreur lors de la creation de la cle.", "error")
        return redirect(url_for("dashboard_dev.api_keys"))

    flash(f"Cle API '{nom}' creee avec succes ! Copiez-la maintenant, elle ne sera plus affichee.", "success")
    return render_template("dashboard/dev/api_keys.html",
                          profile=profile,
                          cles=lister_cles(profile["id"]),
                          nouvelle_cle=full_key,
                          nouvelle_cle_nom=nom)


@dashboard_dev_bp.route("/api-keys/<cle_id>/revoquer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def api_keys_revoquer(cle_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "api_keys")
    if redir_check:
        return redir_check

    ok = revoquer_cle(cle_id, profile["id"])
    if ok:
        flash("Cle API revoquee. Elle ne peut plus etre utilisee.", "success")
    else:
        flash("Erreur lors de la revocation.", "error")
    return redirect(url_for("dashboard_dev.api_keys"))


@dashboard_dev_bp.route("/api-keys/<cle_id>/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def api_keys_supprimer(cle_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "api_keys")
    if redir_check:
        return redir_check

    ok = supprimer_cle(cle_id, profile["id"])
    if ok:
        flash("Cle API supprimee definitivement.", "success")
    else:
        flash("Erreur lors de la suppression.", "error")
    return redirect(url_for("dashboard_dev.api_keys"))


@dashboard_dev_bp.route("/documentation")
@login_required
def documentation():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "documentation")
    if redir_check:
        return redir_check

    return render_template("dashboard/dev/documentation.html", profile=profile)


@dashboard_dev_bp.route("/playground")
@login_required
def playground():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "playground")
    if redir_check:
        return redir_check

    return render_template("dashboard/dev/playground.html", profile=profile)


@dashboard_dev_bp.route("/webhooks")
@login_required
def webhooks():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "webhooks")
    if redir_check:
        return redir_check

    flash("Cette fonctionnalite sera bientot disponible.", "info")
    return redirect(url_for("dashboard_dev.index"))


@dashboard_dev_bp.route("/logs")
@login_required
def logs():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "logs_api")
    if redir_check:
        return redir_check

    flash("Cette fonctionnalite sera bientot disponible.", "info")
    return redirect(url_for("dashboard_dev.index"))


@dashboard_dev_bp.route("/sdk")
@login_required
def sdk():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "sdk")
    if redir_check:
        return redir_check

    flash("Cette fonctionnalite sera bientot disponible.", "info")
    return redirect(url_for("dashboard_dev.index"))