import logging
from flask import Blueprint, render_template, session, redirect, url_for
from app.models.database import get_profile
from app.models.security import login_required

logger = logging.getLogger(__name__)
home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def index():
    """Landing page publique."""
    if "user_id" in session:
        return redirect(url_for("home.dashboard"))
    return render_template("index.html")


@home_bp.route("/dashboard")
@login_required
def dashboard():
    """Dashboard revendeur (ou page d'activation si pas encore revendeur)."""
    user_id = session.get("user_id")
    profile = get_profile(user_id)
    if not profile:
        from app.models.security import clear_session
        clear_session()
        return redirect(url_for("auth.connexion"))
    return render_template("dashboard/index.html", profile=profile)


@home_bp.route("/health")
def health():
    return {"status": "ok", "service": "boost-reseller"}, 200