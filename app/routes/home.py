"""
Routes publiques : accueil, sante, redirection dashboard, pages légales.
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


@home_bp.route("/cgu")
def cgu():
    """Conditions Generales d'Utilisation."""
    return render_template("cgu.html")


@home_bp.route("/confidentialite")
def confidentialite():
    """Politique de Confidentialite."""
    return render_template("confidentialite.html")

@home_bp.route("/health/crypto")
def health_crypto():
    """Vérifie que le système de chiffrement fonctionne (admin only)."""
    from flask import session, jsonify
    from app.models.database import get_profile
    from app.models.crypto import tester_configuration, encrypt, masquer
    import os

    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401
    profile = get_profile(user_id)
    if not profile or not profile.get("est_admin"):
        return jsonify({"error": "forbidden"}), 403

    ok = tester_configuration()
    exemple = None
    if ok:
        chiffre = encrypt("sk_live_example_key_12345")
        exemple = {
            "clair_masque": masquer("sk_live_example_key_12345"),
            "chiffre_extrait": chiffre[:40] + "..." if chiffre else None,
            "longueur_chiffre": len(chiffre) if chiffre else 0,
        }

    return jsonify({
        "crypto_ok": ok,
        "encryption_key_configured": bool(os.environ.get("ENCRYPTION_KEY")),
        "exemple": exemple,
    })