"""
Dashboard développeur — Clés API, webhooks, documentation, playground, logs, sdk, oauth.
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
    """Verifie si le revendeur a acces a la fonctionnalite. Sinon redirect."""
    try:
        if not revendeur_a_feature(profile["id"], code, profile):
            flash("Cette fonctionnalite n'est pas activee sur votre compte.", "warning")
            return redirect(url_for("dashboard_dev.index"))
    except Exception as e:
        logger.error(f"_check_feature {code}: {type(e).__name__}")
    return None


# ═══════════════════════════════════════════════════════════════
# HUB
# ═══════════════════════════════════════════════════════════════

@dashboard_dev_bp.route("/")
@login_required
def index():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    try:
        features = get_features_actives_pour_revendeur(profile["id"], profile)
    except Exception as e:
        logger.error(f"index features: {type(e).__name__}")
        features = []

    return render_template("dashboard/dev/index.html",
                          profile=profile,
                          features=features)


# ═══════════════════════════════════════════════════════════════
# CLES API
# ═══════════════════════════════════════════════════════════════

@dashboard_dev_bp.route("/api-keys")
@login_required
@limiter.limit("30 per hour")
def api_keys():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "api_keys")
    if redir_check:
        return redir_check

    cles = lister_cles(profile["id"])
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
        flash("Erreur lors de la creation.", "error")
        return redirect(url_for("dashboard_dev.api_keys"))

    flash(f"Cle API '{nom}' creee ! Copiez-la maintenant.", "success")
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

    revoquer_cle(cle_id, profile["id"])
    flash("Cle API revoquee.", "success")
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

    supprimer_cle(cle_id, profile["id"])
    flash("Cle API supprimee definitivement.", "success")
    return redirect(url_for("dashboard_dev.api_keys"))


# ═══════════════════════════════════════════════════════════════
# DOCUMENTATION
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# PLAYGROUND
# ═══════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════
# WEBHOOKS
# ═══════════════════════════════════════════════════════════════

@dashboard_dev_bp.route("/webhooks")
@login_required
def webhooks():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "webhooks")
    if redir_check:
        return redir_check

    from app.models.webhooks import lister_webhooks, EVENTS_DISPONIBLES
    return render_template("dashboard/dev/webhooks.html",
                          profile=profile,
                          webhooks=lister_webhooks(profile["id"]),
                          events_dispo=EVENTS_DISPONIBLES)


@dashboard_dev_bp.route("/webhooks/creer", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def webhooks_creer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "webhooks")
    if redir_check:
        return redir_check

    from app.models.webhooks import creer_webhook, lister_webhooks, EVENTS_DISPONIBLES

    url_endpoint = request.form.get("url", "").strip()[:500]
    if not url_endpoint or not url_endpoint.startswith(("http://", "https://")):
        flash("URL invalide. Doit commencer par http:// ou https://", "error")
        return redirect(url_for("dashboard_dev.webhooks"))

    events = request.form.getlist("events")
    events = [e for e in events if e in EVENTS_DISPONIBLES]
    if not events:
        flash("Selectionnez au moins un evenement.", "error")
        return redirect(url_for("dashboard_dev.webhooks"))

    wh, secret = creer_webhook(profile["id"], url_endpoint, events)
    if not wh:
        flash("Erreur lors de la creation.", "error")
        return redirect(url_for("dashboard_dev.webhooks"))

    flash("Webhook cree ! Copiez le secret maintenant.", "success")
    return render_template("dashboard/dev/webhooks.html",
                          profile=profile,
                          webhooks=lister_webhooks(profile["id"]),
                          events_dispo=EVENTS_DISPONIBLES,
                          nouveau_secret=secret)


@dashboard_dev_bp.route("/webhooks/<webhook_id>/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def webhooks_toggle(webhook_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "webhooks")
    if redir_check:
        return redir_check

    from app.models.webhooks import maj_webhook
    actif = request.form.get("actif") == "1"
    maj_webhook(webhook_id, profile["id"], {"actif": not actif})
    flash(f"Webhook {'desactive' if actif else 'active'}.", "success")
    return redirect(url_for("dashboard_dev.webhooks"))


@dashboard_dev_bp.route("/webhooks/<webhook_id>/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def webhooks_supprimer(webhook_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "webhooks")
    if redir_check:
        return redir_check

    from app.models.webhooks import supprimer_webhook
    supprimer_webhook(webhook_id, profile["id"])
    flash("Webhook supprime.", "success")
    return redirect(url_for("dashboard_dev.webhooks"))


@dashboard_dev_bp.route("/webhooks/<webhook_id>/tester", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def webhooks_tester(webhook_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "webhooks")
    if redir_check:
        return redir_check

    from app.models.webhooks import tester_webhook
    succes, message = tester_webhook(webhook_id, profile["id"])
    flash(message, "success" if succes else "error")
    return redirect(url_for("dashboard_dev.webhooks"))


@dashboard_dev_bp.route("/webhooks/<webhook_id>/logs")
@login_required
def webhooks_logs(webhook_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "webhooks")
    if redir_check:
        return redir_check

    from app.models.webhooks import get_webhook, lister_logs
    wh = get_webhook(webhook_id, profile["id"])
    if not wh:
        flash("Webhook introuvable.", "error")
        return redirect(url_for("dashboard_dev.webhooks"))

    return render_template("dashboard/dev/webhooks_logs.html",
                          profile=profile,
                          webhook=wh,
                          logs=lister_logs(webhook_id, limit=100))


# ═══════════════════════════════════════════════════════════════
# LOGS API
# ═══════════════════════════════════════════════════════════════

@dashboard_dev_bp.route("/logs")
@login_required
def logs():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "logs_api")
    if redir_check:
        return redir_check

    return render_template("dashboard/dev/logs.html", profile=profile)


# ═══════════════════════════════════════════════════════════════
# SDK
# ═══════════════════════════════════════════════════════════════

@dashboard_dev_bp.route("/sdk")
@login_required
def sdk():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "sdk")
    if redir_check:
        return redir_check

    return render_template("dashboard/dev/sdk.html", profile=profile)


# ═══════════════════════════════════════════════════════════════
# OAUTH APPS
# ═══════════════════════════════════════════════════════════════

@dashboard_dev_bp.route("/oauth-apps")
@login_required
def oauth_apps():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "oauth_apps")
    if redir_check:
        return redir_check

    from app.models.oauth_apps import lister_apps, SCOPES_DISPONIBLES
    return render_template("dashboard/dev/oauth_apps.html",
                          profile=profile,
                          apps=lister_apps(profile["id"]),
                          scopes_dispo=SCOPES_DISPONIBLES)


@dashboard_dev_bp.route("/oauth-apps/creer", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def oauth_apps_creer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "oauth_apps")
    if redir_check:
        return redir_check

    from app.models.oauth_apps import creer_app, lister_apps, SCOPES_DISPONIBLES

    nom = request.form.get("nom", "").strip()[:80]
    description = request.form.get("description", "").strip()[:500]
    redirect_uris_raw = request.form.get("redirect_uris", "").strip()
    scopes = request.form.getlist("scopes")

    if not nom:
        flash("Le nom de l'application est obligatoire.", "error")
        return redirect(url_for("dashboard_dev.oauth_apps"))

    redirect_uris = [u.strip() for u in redirect_uris_raw.split("\n") if u.strip()]
    redirect_uris = [u for u in redirect_uris if u.startswith(("http://", "https://"))]
    if not redirect_uris:
        flash("Au moins une URL de redirection valide est requise.", "error")
        return redirect(url_for("dashboard_dev.oauth_apps"))

    scopes = [s for s in scopes if s in SCOPES_DISPONIBLES]
    if not scopes:
        flash("Selectionnez au moins un scope.", "error")
        return redirect(url_for("dashboard_dev.oauth_apps"))

    app, client_id, client_secret = creer_app(profile["id"], nom, description, redirect_uris, scopes)
    if not app:
        flash("Erreur lors de la creation.", "error")
        return redirect(url_for("dashboard_dev.oauth_apps"))

    flash("Application creee ! Copiez le client secret maintenant.", "success")
    return render_template("dashboard/dev/oauth_apps.html",
                          profile=profile,
                          apps=lister_apps(profile["id"]),
                          scopes_dispo=SCOPES_DISPONIBLES,
                          nouvelle_app=app,
                          nouveau_client_id=client_id,
                          nouveau_client_secret=client_secret)


@dashboard_dev_bp.route("/oauth-apps/<app_id>/regenerer-secret", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def oauth_apps_regenerer(app_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "oauth_apps")
    if redir_check:
        return redir_check

    from app.models.oauth_apps import regenerer_secret, lister_apps, SCOPES_DISPONIBLES

    nouveau_secret = regenerer_secret(app_id, profile["id"])
    if not nouveau_secret:
        flash("Erreur lors de la regeneration.", "error")
        return redirect(url_for("dashboard_dev.oauth_apps"))

    flash("Nouveau secret genere ! Copiez-le maintenant.", "success")
    return render_template("dashboard/dev/oauth_apps.html",
                          profile=profile,
                          apps=lister_apps(profile["id"]),
                          scopes_dispo=SCOPES_DISPONIBLES,
                          nouveau_client_secret=nouveau_secret,
                          app_concernee_id=app_id)


@dashboard_dev_bp.route("/oauth-apps/<app_id>/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def oauth_apps_toggle(app_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "oauth_apps")
    if redir_check:
        return redir_check

    from app.models.oauth_apps import toggle_app
    actif = request.form.get("actif") == "1"
    toggle_app(app_id, profile["id"], not actif)
    flash(f"Application {'desactivee' if actif else 'activee'}.", "success")
    return redirect(url_for("dashboard_dev.oauth_apps"))


@dashboard_dev_bp.route("/oauth-apps/<app_id>/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def oauth_apps_supprimer(app_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "oauth_apps")
    if redir_check:
        return redir_check

    from app.models.oauth_apps import supprimer_app
    supprimer_app(app_id, profile["id"])
    flash("Application supprimee.", "success")
    return redirect(url_for("dashboard_dev.oauth_apps"))


@dashboard_dev_bp.route("/oauth-apps/<app_id>/logs")
@login_required
def oauth_apps_logs(app_id):
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    redir_check = _check_feature(profile, "oauth_apps")
    if redir_check:
        return redir_check

    from app.models.oauth_apps import lister_apps, lister_logs
    apps = lister_apps(profile["id"])
    app = next((a for a in apps if a["id"] == app_id), None)
    if not app:
        flash("Application introuvable.", "error")
        return redirect(url_for("dashboard_dev.oauth_apps"))

    return render_template("dashboard/dev/oauth_apps_logs.html",
                          profile=profile,
                          app=app,
                          logs=lister_logs(app_id, limit=100))