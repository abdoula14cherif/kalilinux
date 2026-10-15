"""
Authentification SSO par code temporaire + connexion classique.
SÉCURITÉ SÉVÈRE : rate limit, anti-brute-force, anti-bot, logs.
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
    set_session, clear_session, est_bot_fort, verifier_honeypot
)
from app.models.database import get_profile

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)

# Anti-brute-force en mémoire (par email)
_TENTATIVES = {}
MAX_TENTATIVES = 5
FENETRE_MINUTES = 15


def _supabase_auth_url():
    return current_app.config["SUPABASE_URL"] + "/auth/v1"


def _supabase_headers():
    anon = current_app.config["SUPABASE_ANON_KEY"]
    return {"apikey": anon, "Content-Type": "application/json"}


def _est_rate_limited(email):
    maintenant = time.time()
    fenetre = FENETRE_MINUTES * 60
    if email in _TENTATIVES:
        _TENTATIVES[email] = [t for t in _TENTATIVES[email] if maintenant - t < fenetre]
        if len(_TENTATIVES[email]) >= MAX_TENTATIVES:
            return True
    return False


def _enregistrer_tentative(email):
    if email not in _TENTATIVES:
        _TENTATIVES[email] = []
    _TENTATIVES[email].append(time.time())


def _reinitialiser_tentatives(email):
    _TENTATIVES.pop(email, None)


def _log_securite(message, niveau="warning"):
    ip = (request.headers.get("X-Forwarded-For", request.remote_addr or "")).split(",")[0].strip()
    ua = (request.headers.get("User-Agent", "") or "")[:100]
    getattr(logger, niveau)(f"[SECURITE] {message} | IP={ip} | UA={ua}")


@auth_bp.route("/connexion")
@limiter.limit("30 per hour")
def connexion():
    """Affiche la page de connexion."""
    if "user_id" in session:
        return redirect(url_for("home.dashboard_redirect"))
    return render_template("auth/connexion.html")


@auth_bp.route("/sso-redirect")
@limiter.limit("20 per hour")
def sso_redirect():
    """
    Redirige vers Boost Central pour initier le SSO.
    Boost Central generera un code temporaire et nous redirigera vers /auth/sso?code=XXX
    """
    client_url = current_app.config.get("CLIENT_URL", "https://boostcentral.world")
    return_url = url_for("auth.sso_callback", _external=True)
    _log_securite("SSO redirect initie", "info")
    return redirect(f"{client_url}/auth/sso-login?redirect={return_url}")


@auth_bp.route("/sso")
@limiter.limit("30 per hour")
def sso_callback():
    """
    Recupere un code SSO temporaire genere par Boost Central.
    SÉCURITÉ : code usage unique, expire en 2 minutes, anti-replay.
    """
    from app.models.sso import utiliser_code_sso

    # Blocage des bots
    if est_bot_fort():
        _log_securite("Bot detecte sur SSO", "warning")
        flash("Acces refuse.", "error")
        return redirect(url_for("auth.connexion"))

    code = request.args.get("code", "").strip()
    if not code:
        _log_securite("SSO sans code", "warning")
        flash("Lien de connexion invalide.", "error")
        return redirect(url_for("auth.connexion"))

    payload = utiliser_code_sso(code)
    if not payload:
        _log_securite("SSO code invalide/expire/rejoue", "warning")
        flash("Lien SSO expire ou invalide. Reconnectez-vous.", "error")
        return redirect(url_for("auth.connexion"))

    user_id = payload.get("user_id")
    email = payload.get("email")

    if not user_id or not email:
        _log_securite("SSO payload incomplet", "warning")
        flash("Donnees SSO incompletes.", "error")
        return redirect(url_for("auth.connexion"))

    profile = get_profile(user_id)
    if not profile:
        _log_securite(f"SSO user introuvable : {email}", "warning")
        flash("Utilisateur introuvable.", "error")
        return redirect(url_for("auth.connexion"))

    if profile.get("banni"):
        _log_securite(f"SSO compte banni : {email}", "error")
        flash("Votre compte a ete suspendu. Contactez le support.", "error")
        return redirect(url_for("auth.connexion"))

    full_name = payload.get("full_name") or profile.get("full_name") or email.split("@")[0]
    set_session(user_id, email, full_name)
    _log_securite(f"SSO succes : {email}", "info")

    flash(f"Bienvenue {full_name.split()[0]} !", "success")
    return redirect(url_for("home.dashboard_redirect"))


@auth_bp.route("/login-classique", methods=["POST"])
@limiter.limit("10 per minute; 30 per hour; 100 per day")
def login_classique():
    """
    Connexion email + mot de passe.
    SÉCURITÉ : rate limit IP + anti-brute-force email + honeypot + anti-bot.
    """
    # Anti-bot
    if est_bot_fort():
        _log_securite("Bot detecte sur login-classique", "warning")
        flash("Erreur de connexion.", "error")
        return redirect(url_for("auth.connexion"))

    # Honeypot
    if not verifier_honeypot():
        _log_securite("Honeypot declenche sur login", "warning")
        flash("Erreur de connexion.", "error")
        return redirect(url_for("auth.connexion"))

    email = request.form.get("email", "").strip().lower()[:150]
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email et mot de passe requis.", "error")
        return redirect(url_for("auth.connexion"))

    if "@" not in email or len(email) < 5:
        _log_securite(f"Email invalide : {email}", "warning")
        flash("Email invalide.", "error")
        return redirect(url_for("auth.connexion"))

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

            profile = get_profile(user_id)
            if profile and profile.get("banni"):
                _log_securite(f"Login compte banni : {email}", "error")
                flash("Votre compte a ete suspendu. Contactez le support.", "error")
                return redirect(url_for("auth.connexion"))

            _reinitialiser_tentatives(email)
            set_session(user_id, email, full_name)
            _log_securite(f"Login succes : {email}", "info")
            flash(f"Bienvenue {full_name.split()[0]} !", "success")
            return redirect(url_for("home.dashboard_redirect"))
        else:
            _enregistrer_tentative(email)
            msg = data.get("error_description", data.get("msg", "Email ou mot de passe incorrect."))
            _log_securite(f"Login echoue : {email} - {msg}", "warning")
            flash(f"Erreur : {msg}", "error")
    except requests.Timeout:
        _log_securite(f"Login timeout : {email}", "error")
        flash("Le serveur met trop de temps a repondre.", "error")
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