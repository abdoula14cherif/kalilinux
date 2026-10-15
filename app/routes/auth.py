"""
Authentification SSO avec Boost Central + connexion classique.
SÉCURITÉ SÉVÈRE : rate limit, logging, anti-brute-force.
"""
import logging
import time
import requests
from flask import (
    Blueprint, render_template, redirect, url_for, flash,
    session, request, current_app
)
from app import limiter
from app.models.security import (
    set_session, clear_session, verifier_token_sso
)
from app.models.database import get_profile

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)

# Anti-brute-force en mémoire (par email)
_TENTATIVES = {}  # {email: [timestamps]}
MAX_TENTATIVES = 5
FENETRE_MINUTES = 15


def _supabase_auth_url():
    return current_app.config["SUPABASE_URL"] + "/auth/v1"


def _supabase_headers():
    anon = current_app.config["SUPABASE_ANON_KEY"]
    return {"apikey": anon, "Content-Type": "application/json"}


def _est_rate_limited(email):
    """Verifie si l'email a trop de tentatives recentes."""
    maintenant = time.time()
    fenetre = FENETRE_MINUTES * 60
    if email in _TENTATIVES:
        # Nettoie les vieilles tentatives
        _TENTATIVES[email] = [t for t in _TENTATIVES[email] if maintenant - t < fenetre]
        if len(_TENTATIVES[email]) >= MAX_TENTATIVES:
            return True
    return False


def _enregistrer_tentative(email):
    """Enregistre une tentative de connexion."""
    if email not in _TENTATIVES:
        _TENTATIVES[email] = []
    _TENTATIVES[email].append(time.time())


def _reinitialiser_tentatives(email):
    """Reinitialise les tentatives apres un succes."""
    _TENTATIVES.pop(email, None)


def _log_securite(message, niveau="warning"):
    """Log de securite avec IP."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    ua = request.headers.get("User-Agent", "")[:100]
    getattr(logger, niveau)(f"[SECURITE] {message} | IP={ip} | UA={ua}")


@auth_bp.route("/connexion")
@limiter.limit("30 per hour")
def connexion():
    """Affiche la page de connexion."""
    if "user_id" in session:
        return redirect(url_for("home.dashboard"))
    return render_template("auth/connexion.html")


@auth_bp.route("/sso-redirect")
@limiter.limit("20 per hour")
def sso_redirect():
    """Redirige vers boostcentral pour lancer le SSO."""
    client_url = current_app.config.get("CLIENT_URL", "https://boostcentral.world")
    return_url = url_for("auth.sso_callback", _external=True)
    _log_securite(f"SSO redirect initie", "info")
    return redirect(f"{client_url}/auth/sso-login?redirect={return_url}")


@auth_bp.route("/sso")
@limiter.limit("30 per hour")
def sso_callback():
    """Recoit le JWT signe par boostcentral."""
    token = request.args.get("token", "").strip()
    if not token:
        _log_securite("SSO sans token", "warning")
        flash("Lien SSO invalide.", "error")
        return redirect(url_for("auth.connexion"))

    payload = verifier_token_sso(token)
    if not payload:
        _log_securite("SSO token invalide ou expire", "warning")
        flash("Lien SSO expire ou invalide. Reconnectez-vous.", "error")
        return redirect(url_for("auth.connexion"))

    user_id = payload.get("user_id")
    email = payload.get("email")

    if not user_id or not email:
        _log_securite("SSO payload incomplet", "warning")
        flash("Donnees SSO incompletes.", "error")
        return redirect(url_for("auth.connexion"))

    # Verifier que le compte n'est pas banni
    profile = get_profile(user_id)
    if not profile:
        _log_securite(f"SSO user introuvable : {email}", "warning")
        flash("Utilisateur introuvable sur Boost Central.", "error")
        return redirect(url_for("auth.connexion"))

    if profile.get("banni"):
        _log_securite(f"SSO compte banni : {email}", "error")
        flash("Votre compte a ete suspendu. Contactez le support.", "error")
        return redirect(url_for("auth.connexion"))

    full_name = profile.get("full_name") or email.split("@")[0]
    set_session(user_id, email, full_name)
    _log_securite(f"SSO succes : {email}", "info")

    flash(f"Bienvenue {full_name.split()[0]} !", "success")
    return redirect(url_for("home.dashboard"))


@auth_bp.route("/login-classique", methods=["POST"])
@limiter.limit("10 per minute; 30 per hour; 100 per day")
def login_classique():
    """
    Connexion email + mot de passe via Supabase Auth.
    SÉCURITÉ : rate limit par IP + anti-brute-force par email.
    """
    email = request.form.get("email", "").strip().lower()[:150]
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email et mot de passe requis.", "error")
        return redirect(url_for("auth.connexion"))

    # Validation format email
    if "@" not in email or len(email) < 5:
        _log_securite(f"Email invalide : {email}", "warning")
        flash("Email invalide.", "error")
        return redirect(url_for("auth.connexion"))

    # Anti-brute-force par email
    if _est_rate_limited(email):
        _log_securite(f"Brute-force detecte : {email}", "error")
        flash(f"Trop de tentatives. Reessayez dans {FENETRE_MINUTES} minutes.", "error")
        return redirect(url_for("auth.connexion"))

    try:
        r = requests.post(
            f"{_supabase_auth_url()}/token?grant_type=password",
            json={"email": email, "password": password},
            headers=_supabase_headers(),
            timeout=15
        )
        data = r.json()

        if r.status_code == 200 and "access_token" in data:
            user = data.get("user", {})
            user_id = user.get("id")
            meta = user.get("user_metadata", {})
            full_name = meta.get("full_name", email.split("@")[0])

            if not user_id:
                _log_securite(f"Login sans user_id : {email}", "error")
                flash("Erreur de connexion.", "error")
                return redirect(url_for("auth.connexion"))

            # Verifier que le compte n'est pas banni
            profile = get_profile(user_id)
            if profile and profile.get("banni"):
                _log_securite(f"Login compte banni : {email}", "error")
                flash("Votre compte a ete suspendu. Contactez le support.", "error")
                return redirect(url_for("auth.connexion"))

            _reinitialiser_tentatives(email)
            set_session(user_id, email, full_name)
            _log_securite(f"Login succes : {email}", "info")
            flash(f"Bienvenue {full_name.split()[0]} !", "success")
            return redirect(url_for("home.dashboard"))
        else:
            _enregistrer_tentative(email)
            msg = data.get("error_description", data.get("msg", "Email ou mot de passe incorrect."))
            _log_securite(f"Login echoue : {email} - {msg}", "warning")
            flash(f"Erreur : {msg}", "error")
    except requests.Timeout:
        _log_securite(f"Login timeout : {email}", "error")
        flash("Le serveur met trop de temps a repondre. Reessayez.", "error")
    except Exception as e:
        _log_securite(f"Login exception : {email} - {type(e).__name__}", "error")
        flash("Erreur serveur. Reessayez.", "error")

    return redirect(url_for("auth.connexion"))


@auth_bp.route("/logout")
@limiter.limit("30 per hour")
def logout():
    email = session.get("user_email", "?")
    clear_session()
    _log_securite(f"Logout : {email}", "info")
    flash("Vous etes deconnecte.", "success")
    return redirect(url_for("home.index"))