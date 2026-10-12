"""
Dashboard revendeur — toutes les pages de l'espace revendeur.
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app.models.security import login_required
from app.models.database import (
    get_profile, update_profile, get_active_services,
    get_revendeur_prix_all, set_revendeur_prix,
    get_revendeur_clients_detail, get_revendeur_orders,
    get_revendeur_gains_total
)
from app.models.storage import upload_image

logger = logging.getLogger(__name__)
dashboard_bp = Blueprint("dashboard", __name__)

THEMES = {
    "bleu":   ("#0066FF", "#0047CC"),
    "violet": ("#7C3AED", "#4C1D95"),
    "vert":   ("#059669", "#047857"),
    "orange": ("#F97316", "#EA580C"),
    "noir":   ("#0F172A", "#1E293B"),
    "rouge":  ("#DC2626", "#991B1B"),
}


def _get_profile_ou_redirect():
    user_id = session.get("user_id")
    if not user_id:
        return None, redirect(url_for("auth.connexion"))
    profile = get_profile(user_id)
    if not profile:
        from app.models.security import clear_session
        clear_session()
        return None, redirect(url_for("auth.connexion"))
    return profile, None


# ═══════════════════════════════════════════════════════════════
# ACCUEIL
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/")
@login_required
def index():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/index.html", profile=profile)


# ═══════════════════════════════════════════════════════════════
# BOUTIQUE (personnalisation)
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/boutique")
@login_required
def boutique():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/boutique.html", profile=profile, themes=THEMES)


@dashboard_bp.route("/boutique/enregistrer", methods=["POST"])
@login_required
def boutique_enregistrer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    user_id = profile["id"]
    data = {}

    # ─── Textes ───
    data["boutique_nom"] = request.form.get("boutique_nom", "").strip() or None
    data["boutique_slogan"] = request.form.get("boutique_slogan", "").strip() or None
    data["boutique_message_accueil"] = request.form.get("boutique_message_accueil", "").strip() or None
    data["boutique_a_propos"] = request.form.get("boutique_a_propos", "").strip() or None

    # ─── Contact ───
    data["boutique_whatsapp"] = request.form.get("boutique_whatsapp", "").strip() or None
    data["boutique_email"] = request.form.get("boutique_email", "").strip() or None

    # ─── Réseaux sociaux + visibilité ───
    data["boutique_facebook"] = request.form.get("boutique_facebook", "").strip() or None
    data["boutique_instagram"] = request.form.get("boutique_instagram", "").strip() or None
    data["boutique_tiktok"] = request.form.get("boutique_tiktok", "").strip() or None
    data["boutique_telegram"] = request.form.get("boutique_telegram", "").strip() or None

    # ─── Thème ───
    theme = request.form.get("boutique_theme", "bleu")
    if theme in THEMES:
        data["boutique_theme"] = theme
        data["boutique_couleur_principale"] = THEMES[theme][0]
        data["boutique_couleur_secondaire"] = THEMES[theme][1]

    # ─── Options ───
    data["boutique_afficher_prix"] = request.form.get("boutique_afficher_prix") == "on"
    data["boutique_whatsapp_flottant"] = request.form.get("boutique_whatsapp_flottant") == "on"

    # ─── Upload logo ───
    logo_file = request.files.get("boutique_logo")
    if logo_file and logo_file.filename:
        logo_url = upload_image(logo_file, prefix="logo_")
        if logo_url:
            data["boutique_logo_url"] = logo_url
        else:
            flash("Erreur lors de l'upload du logo.", "warning")

    # ─── Upload bannière ───
    banniere_file = request.files.get("boutique_banniere")
    if banniere_file and banniere_file.filename:
        banniere_url = upload_image(banniere_file, prefix="banniere_")
        if banniere_url:
            data["boutique_banniere_url"] = banniere_url
        else:
            flash("Erreur lors de l'upload de la banniere.", "warning")

    ok = update_profile(user_id, data)
    if ok:
        flash("✅ Boutique mise a jour !", "success")
    else:
        flash("Erreur lors de la sauvegarde.", "error")

    return redirect(url_for("dashboard.boutique"))


@dashboard_bp.route("/boutique/supprimer-image", methods=["POST"])
@login_required
def boutique_supprimer_image():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    type_img = request.form.get("type", "")
    if type_img == "logo":
        update_profile(profile["id"], {"boutique_logo_url": None})
        flash("Logo supprime.", "success")
    elif type_img == "banniere":
        update_profile(profile["id"], {"boutique_banniere_url": None})
        flash("Banniere supprimee.", "success")

    return redirect(url_for("dashboard.boutique"))


# ═══════════════════════════════════════════════════════════════
# AUTRES PAGES (placeholders)
# ═══════════════════════════════════════════════════════════════

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