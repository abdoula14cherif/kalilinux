"""
Dashboard revendeur — toutes les pages de l'espace revendeur.
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for
from app.models.security import login_required
from app.models.database import get_profile

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)


def _get_profile_ou_redirect():
    """Recupere le profil ou redirige vers la connexion."""
    user_id = session.get("user_id")
    if not user_id:
        return None, redirect(url_for("auth.connexion"))
    profile = get_profile(user_id)
    if not profile:
        from app.models.security import clear_session
        clear_session()
        return None, redirect(url_for("auth.connexion"))
    return profile, None


@dashboard_bp.route("/")
@login_required
def index():
    """Page d'accueil du dashboard revendeur."""
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/index.html", profile=profile)


@dashboard_bp.route("/boutique")
@login_required
def boutique():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/boutique.html", profile=profile)


@dashboard_bp.route("/prix")
@login_required
def prix():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/prix.html", profile=profile)


@dashboard_bp.route("/clients")
@login_required
def clients():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/clients.html", profile=profile)


@dashboard_bp.route("/commandes")
@login_required
def commandes():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/commandes.html", profile=profile)


@dashboard_bp.route("/gains")
@login_required
def gains():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/gains.html", profile=profile)


@dashboard_bp.route("/abonnement")
@login_required
def abonnement():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/abonnement.html", profile=profile)


@dashboard_bp.route("/publier")
@login_required
def publier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/publier.html", profile=profile)


@dashboard_bp.route("/parametres")
@login_required
def parametres():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/parametres.html", profile=profile)