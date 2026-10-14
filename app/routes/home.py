"""
Routes publiques : accueil, sante, redirection dashboard.
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for
from app.models.security import login_required
from app.models.database import get_profile

logger = logging.getLogger(__name__)
home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def index():
    """Landing page publique."""
    if "user_id" in session:
        return redirect(url_for("dashboard.index"))
    return render_template("index.html")


@home_bp.route("/dashboard")
def dashboard_redirect():
    """Redirige vers le vrai dashboard (garde la compatibilite)."""
    if "user_id" not in session:
        return redirect(url_for("auth.connexion"))
    return redirect(url_for("dashboard.index"))


@home_bp.route("/health")
def health():
    """Endpoint de sante pour Vercel."""
    return {"status": "ok", "service": "boost-reseller"}, 200
