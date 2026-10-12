"""
Authentification SSO avec Boost Central + connexion classique (2e visite).
"""
import logging
import requests
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    session, request, current_app
)
from app.models.security import (
    set_session, clear_session, verifier_token_sso
)
from app.models.database import get_profile

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)


def _supabase_auth_url():
    return current_app.config["SUPABASE_URL"] + "/auth/v1"


def _supabase_headers():
    anon = current_app.config["SUPABASE_ANON_KEY"]
    return {"apikey": anon, "Content-Type": "application/json"}


# ─── Page de connexion ─────────────────────────────────────────

@auth_bp.route("/connexion")
def connexion():
    """Affiche la page de connexion (SSO + formulaire classique)."""
    if "user_id" in session:
        return redirect(url_for("home.dashboard"))
    return render_template("auth/connexion.html")


# ─── SSO : Bouton "Se connecter avec Boost Central" ────────────

@auth_bp.route("/sso-redirect")
def sso_redirect():
    """
    Redirige vers boostcentral pour lancer le SSO.
    boostcentral generera un JWT et nous renverra ici avec le token.
    """
    client_url = current_app.config.get("CLIENT_URL", "https://boostcentral.world")
    # On transmet notre URL de retour pour que boostcentral sache ou rediriger
    return_url = url_for("auth.sso_callback", _external=True)
    return redirect(f"{client_url}/auth/sso-login?redirect={return_url}")


# ─── SSO : Reception du JWT ────────────────────────────────────

@auth_bp.route("/sso")
def sso_callback():
    """
    Recoit le JWT signe par boostcentral, le verifie, cree la session.
    """
    token = request.args.get("token", "").strip()
    if not token:
        flash("Lien SSO invalide.", "error")
        return redirect(url_for("auth.connexion"))

    payload = verifier_token_sso(token)
    if not payload:
        flash("Lien SSO expire ou invalide. Reconnectez-vous.", "error")
        return redirect(url_for("auth.connexion"))

    user_id = payload.get("user_id")
    email = payload.get("email")

    if not user_id or not email:
        flash("Donnees SSO incompletes.", "error")
        return redirect(url_for("auth.connexion"))

    # Recuperer les infos completes depuis Supabase
    profile = get_profile(user_id)
    if not profile:
        flash("Utilisateur introuvable sur Boost Central.", "error")
        return redirect(url_for("auth.connexion"))

    full_name = profile.get("full_name") or email.split("@")[0]

    # Creer la session locale
    set_session(user_id, email, full_name)

    flash(f"Bienvenue {full_name.split()[0]} !", "success")
    return redirect(url_for("home.dashboard"))


# ─── Connexion classique (2e visite et +) ──────────────────────

@auth_bp.route("/login-classique", methods=["POST"])
def login_classique():
    """
    Connexion avec email + mot de passe (via Supabase Auth).
    Utilise les memes identifiants que boostcentral.
    """
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email et mot de passe requis.", "error")
        return redirect(url_for("auth.connexion"))

    try:
        r = requests.post(
            f"{_supabase_auth_url()}/token?grant_type=password",
            json={"email": email, "password": password},
            headers=_supabase_headers()
        )
        data = r.json()

        if r.status_code == 200 and "access_token" in data:
            user = data.get("user", {})
            user_id = user.get("id")
            meta = user.get("user_metadata", {})
            full_name = meta.get("full_name", email.split("@")[0])

            set_session(user_id, email, full_name)
            flash(f"Bienvenue {full_name.split()[0]} !", "success")
            return redirect(url_for("home.dashboard"))
        else:
            msg = data.get("error_description", data.get("msg", "Email ou mot de passe incorrect."))
            flash(f"Erreur : {msg}", "error")
    except Exception as e:
        logger.error(f"login_classique: {e}")
        flash("Erreur serveur. Reessayez.", "error")

    return redirect(url_for("auth.connexion"))


# ─── Deconnexion ───────────────────────────────────────────────

@auth_bp.route("/logout")
def logout():
    clear_session()
    flash("Vous etes deconnecte.", "success")
    return redirect(url_for("home.index"))