"""
Dashboard revendeur — toutes les pages de l'espace revendeur.
"""
import logging
import re
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app.models.security import login_required
from app.models.database import (
    get_profile, update_profile, get_active_services,
    get_revendeur_prix_all, set_revendeur_prix, get_service_by_id,
    get_revendeur_clients_detail, get_revendeur_orders,
    get_revendeur_gains_total, slug_deja_pris,
    debit_balance, credit_balance, activer_revendeur
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

PRIX_ACTIVATION = 5000


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
# BOUTIQUE
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
    logger.info(f"=== SAUVEGARDE BOUTIQUE pour user {user_id} ===")

    data = {}

    # Textes
    data["boutique_nom"] = request.form.get("boutique_nom", "").strip() or None
    data["boutique_slogan"] = request.form.get("boutique_slogan", "").strip() or None
    data["boutique_message_accueil"] = request.form.get("boutique_message_accueil", "").strip() or None
    data["boutique_a_propos"] = request.form.get("boutique_a_propos", "").strip() or None

    # Contact
    data["boutique_whatsapp"] = request.form.get("boutique_whatsapp", "").strip() or None
    data["boutique_email"] = request.form.get("boutique_email", "").strip() or None

    # Reseaux
    data["boutique_facebook"] = request.form.get("boutique_facebook", "").strip() or None
    data["boutique_instagram"] = request.form.get("boutique_instagram", "").strip() or None
    data["boutique_tiktok"] = request.form.get("boutique_tiktok", "").strip() or None
    data["boutique_telegram"] = request.form.get("boutique_telegram", "").strip() or None

    # Theme
    theme = request.form.get("boutique_theme", "bleu")
    if theme in THEMES:
        data["boutique_theme"] = theme
        data["boutique_couleur_principale"] = THEMES[theme][0]
        data["boutique_couleur_secondaire"] = THEMES[theme][1]

    # Options
    data["boutique_afficher_prix"] = request.form.get("boutique_afficher_prix") == "on"
    data["boutique_whatsapp_flottant"] = request.form.get("boutique_whatsapp_flottant") == "on"

    # Upload logo
    logo_file = request.files.get("boutique_logo")
    if logo_file and logo_file.filename:
        try:
            logo_url = upload_image(logo_file, prefix="logo_")
            if logo_url:
                data["boutique_logo_url"] = logo_url
            else:
                flash("Erreur upload logo.", "warning")
        except Exception as e:
            logger.error(f"Logo exception: {e}")
            flash("Erreur upload logo.", "warning")

    # Upload banniere
    banniere_file = request.files.get("boutique_banniere")
    if banniere_file and banniere_file.filename:
        try:
            banniere_url = upload_image(banniere_file, prefix="banniere_")
            if banniere_url:
                data["boutique_banniere_url"] = banniere_url
            else:
                flash("Erreur upload banniere.", "warning")
        except Exception as e:
            logger.error(f"Banniere exception: {e}")
            flash("Erreur upload banniere.", "warning")

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
# PUBLIER (activation du compte revendeur)
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/publier")
@login_required
def publier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    etapes_ok = {
        "nom": bool(profile.get("boutique_nom")),
        "whatsapp": bool(profile.get("boutique_whatsapp")),
        "logo_ou_slogan": bool(profile.get("boutique_logo_url") or profile.get("boutique_slogan")),
    }

    return render_template(
        "dashboard/publier.html",
        profile=profile,
        prix_activation=PRIX_ACTIVATION,
        etapes_ok=etapes_ok,
    )


@dashboard_bp.route("/publier/activer", methods=["POST"])
@login_required
def publier_activer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if profile.get("est_revendeur"):
        flash("Votre boutique est deja publiee.", "info")
        return redirect(url_for("dashboard.index"))

    balance = profile.get("balance", 0) or 0
    if balance < PRIX_ACTIVATION:
        flash(
            f"Solde insuffisant. Il vous faut {PRIX_ACTIVATION:,.0f} FCFA "
            f"(solde actuel : {balance:,.0f} FCFA). Rechargez votre compte Boost Central.",
            "error",
        )
        return redirect(url_for("dashboard.publier"))

    slug = request.form.get("slug", "").strip().lower()
    if not slug or len(slug) < 3 or len(slug) > 30:
        flash("Identifiant invalide : 3 a 30 caracteres.", "error")
        return redirect(url_for("dashboard.publier"))

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,28}[a-z0-9]", slug):
        flash("Identifiant invalide : lettres minuscules, chiffres et tirets uniquement.", "error")
        return redirect(url_for("dashboard.publier"))

    modele = request.form.get("modele", "")
    if modele not in ("marge", "commission"):
        flash("Choisissez un modele de gain.", "error")
        return redirect(url_for("dashboard.publier"))

    if slug_deja_pris(slug):
        flash("Cet identifiant est deja pris. Choisissez-en un autre.", "error")
        return redirect(url_for("dashboard.publier"))

    nouveau_solde = debit_balance(profile["id"], PRIX_ACTIVATION)
    if nouveau_solde is None:
        flash("Erreur lors du paiement. Verifiez votre solde.", "error")
        return redirect(url_for("dashboard.publier"))

    commission = 0.10 if modele == "commission" else 0.0
    ok = activer_revendeur(profile["id"], slug, modele, commission)

    if ok:
        flash(f"🎉 Felicitations ! Votre boutique est en ligne : /r/{slug}", "success")
        return redirect(url_for("dashboard.index"))
    else:
        credit_balance(profile["id"], PRIX_ACTIVATION)
        flash("Erreur lors de l'activation. Vous avez ete rembourse.", "error")
        return redirect(url_for("dashboard.publier"))


# ═══════════════════════════════════════════════════════════════
# PRIX
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/prix")
@login_required
def prix():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    services = get_active_services()
    mes_prix = {}
    try:
        for p in get_revendeur_prix_all(profile["id"]):
            mes_prix[p["service_id"]] = p["prix_fcfa"]
    except Exception as e:
        logger.error(f"prix load: {e}")

    return render_template(
        "dashboard/prix.html",
        profile=profile,
        services=services,
        mes_prix=mes_prix,
    )


@dashboard_bp.route("/prix/enregistrer", methods=["POST"])
@login_required
def prix_enregistrer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    service_id = request.form.get("service_id", "")
    prix_str = request.form.get("prix_fcfa", "").strip()

    try:
        service_id = int(service_id)
        prix_fcfa = float(prix_str)
        if prix_fcfa <= 0:
            raise ValueError
    except Exception:
        flash("Valeurs invalides.", "error")
        return redirect(url_for("dashboard.prix"))

    service = get_service_by_id(service_id)
    if not service:
        flash("Service introuvable.", "error")
        return redirect(url_for("dashboard.prix"))

    if prix_fcfa < float(service["prix_fcfa"]):
        flash(
            f"Votre prix doit etre superieur ou egal au prix de base "
            f"({service['prix_fcfa']} FCFA).",
            "error",
        )
        return redirect(url_for("dashboard.prix"))

    ok = set_revendeur_prix(profile["id"], service_id, prix_fcfa)
    if ok:
        flash("Prix enregistre.", "success")
    else:
        flash("Erreur lors de l'enregistrement.", "error")

    return redirect(url_for("dashboard.prix"))


# ═══════════════════════════════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/clients")
@login_required
def clients():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    mes_clients = []
    try:
        mes_clients = get_revendeur_clients_detail(profile["id"])
    except Exception as e:
        logger.error(f"clients load: {e}")

    return render_template(
        "dashboard/clients.html",
        profile=profile,
        mes_clients=mes_clients,
    )


# ═══════════════════════════════════════════════════════════════
# COMMANDES
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/commandes")
@login_required
def commandes():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    orders = []
    try:
        orders = get_revendeur_orders(profile["id"], limit=200)
    except Exception as e:
        logger.error(f"commandes load: {e}")

    return render_template(
        "dashboard/commandes.html",
        profile=profile,
        orders=orders,
    )


# ═══════════════════════════════════════════════════════════════
# GAINS
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/gains")
@login_required
def gains():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    gains_total = 0
    try:
        gains_total = get_revendeur_gains_total(profile["id"])
    except Exception as e:
        logger.error(f"gains load: {e}")

    return render_template(
        "dashboard/gains.html",
        profile=profile,
        gains_total=gains_total,
    )


# ═══════════════════════════════════════════════════════════════
# ABONNEMENT
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/abonnement")
@login_required
def abonnement():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/abonnement.html", profile=profile)


# ═══════════════════════════════════════════════════════════════
# PARAMETRES
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/parametres")
@login_required
def parametres():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/parametres.html", profile=profile)