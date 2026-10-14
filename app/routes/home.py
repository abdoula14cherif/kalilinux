"""
Routes publiques : accueil, sante, redirection dashboard.
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for

logger = logging.getLogger(__name__)
home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard.index"))
    return render_template("index.html")


@home_bp.route("/dashboard")
def dashboard_redirect():
    if "user_id" not in session:
        return redirect(url_for("auth.connexion"))
    return redirect(url_for("dashboard.index"))


@home_bp.route("/health")
def health():
    return {"status": "ok", "service": "boost-reseller"}, 200