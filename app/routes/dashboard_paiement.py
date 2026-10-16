"""
Dashboard revendeur — Configuration des moyens de paiement.
SÉCURITÉ :
- Pays verrouillé à la 1ère validation (impossible de changer seul)
- Clés API chiffrées en DB
- Test obligatoire avant activation
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app import limiter
from app.models.security import login_required
from app.models.database import (
    get_profile, update_profile,
    set_pays_revendeur, get_pays_revendeur,
)
from app.models.paiement_config import (
    get_tous_pays, get_pays_by_code,
    get_moyens_pour_pays,
    get_config_revendeur, get_config_decryptee_masquee,
    save_config_revendeur, toggle_config_actif,
    supprimer_config_revendeur,
    METHODES_VALIDES,
    methode_est_valide,
)

logger = logging.getLogger(__name__)
dashboard_paiement_bp = Blueprint("dashboard_paiement", __name__)


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


# ═══════════════════════════════════════════════════════════════
# PAGE PRINCIPALE
# ═══════════════════════════════════════════════════════════════

@dashboard_paiement_bp.route("/paiement")
@login_required
def index():
    """
    Page de configuration des paiements.
    - Si pays non défini → écran de choix du pays
    - Sinon → écran de configuration des moyens
    """
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    pays_code = profile.get("pays_code")

    # Cas 1 : pas de pays défini → on affiche le choix
    if not pays_code:
        pays_liste = get_tous_pays()
        return render_template(
            "dashboard/paiement/choix_pays.html",
            profile=profile,
            pays_liste=pays_liste,
        )

    # Cas 2 : pays défini → on affiche les moyens
    pays = get_pays_by_code(pays_code)
    moyens_disponibles = get_moyens_pour_pays(pays_code)
    mes_configs = get_config_revendeur(profile["id"])

    # Dict {method: config_row}
    configs_par_method = {c["method"]: c for c in mes_configs}

    # Enrichir les moyens avec leur config actuelle
    moyens_enrichis = []
    for m in moyens_disponibles:
        method = m["method"]
        config_actuelle = None
        if method in configs_par_method:
            config_actuelle = get_config_decryptee_masquee(profile["id"], method)

        moyens_enrichis.append({
            **m,
            "config_actuelle": config_actuelle,
            "configure": config_actuelle is not None,
            "actif": config_actuelle.get("actif") if config_actuelle else False,
            "test_ok": config_actuelle.get("test_ok") if config_actuelle else False,
        })

    return render_template(
        "dashboard/paiement/index.html",
        profile=profile,
        pays=pays,
        pays_code=pays_code,
        moyens=moyens_enrichis,
    )


# ═══════════════════════════════════════════════════════════════
# CHOIX DU PAYS (verrouillage)
# ═══════════════════════════════════════════════════════════════

@dashboard_paiement_bp.route("/paiement/pays", methods=["POST"])
@login_required
@limiter.limit("5 per hour")
def choisir_pays():
    """Définit le pays du revendeur. Action IRRÉVERSIBLE."""
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if profile.get("pays_verrouille"):
        flash("Votre pays est deja verrouille. Contactez l'administrateur pour le modifier.", "error")
        return redirect(url_for("dashboard_paiement.index"))

    pays_code = request.form.get("pays_code", "").strip().upper()

    if not pays_code or not get_pays_by_code(pays_code):
        flash("Pays invalide.", "error")
        return redirect(url_for("dashboard_paiement.index"))

    # Double confirmation obligatoire
    confirmation = request.form.get("confirmation", "").strip()
    if confirmation != "OUI":
        flash("Vous devez cocher la confirmation pour valider votre pays.", "error")
        return redirect(url_for("dashboard_paiement.index"))

    ok, err = set_pays_revendeur(profile["id"], pays_code)

    if ok:
        pays = get_pays_by_code(pays_code)
        flash(f"Votre pays ({pays['nom']}) est maintenant verrouille. Configurez vos moyens de paiement.", "success")
    else:
        flash(f"Erreur : {err}", "error")

    return redirect(url_for("dashboard_paiement.index"))


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION D'UNE MÉTHODE
# ═══════════════════════════════════════════════════════════════

@dashboard_paiement_bp.route("/paiement/<method>/configurer", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour")
def configurer(method):
    """Page de configuration d'une méthode de paiement."""
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if not methode_est_valide(method):
        flash("Methode de paiement invalide.", "error")
        return redirect(url_for("dashboard_paiement.index"))

    if not profile.get("pays_code"):
        flash("Definissez d'abord votre pays.", "warning")
        return redirect(url_for("dashboard_paiement.index"))

    # Vérifier que la méthode est dispo dans son pays
    moyens_pays = [m["method"] for m in get_moyens_pour_pays(profile["pays_code"])]
    if method not in moyens_pays:
        flash("Cette methode n'est pas disponible dans votre pays.", "error")
        return redirect(url_for("dashboard_paiement.index"))

    methode_info = METHODES_VALIDES[method]

    if request.method == "POST":
        # Récupérer les champs
        config_data = {}
        for champ in methode_info.get("champs_requis", []):
            valeur = request.form.get(champ, "").strip()
            if not valeur:
                flash(f"Le champ '{champ}' est obligatoire.", "error")
                return redirect(url_for("dashboard_paiement.configurer", method=method))
            config_data[champ] = valeur

        # Sauvegarder
        ok, err = save_config_revendeur(profile["id"], method, config_data, actif=False)

        if ok:
            flash(f"Configuration {methode_info['nom']} sauvegardee. Testez-la pour l'activer.", "success")
            return redirect(url_for("dashboard_paiement.index"))
        else:
            flash(f"Erreur : {err}", "error")
            return redirect(url_for("dashboard_paiement.configurer", method=method))

    # GET : afficher le formulaire
    config_actuelle = get_config_decryptee_masquee(profile["id"], method)

    return render_template(
        "dashboard/paiement/configurer.html",
        profile=profile,
        method=method,
        methode_info=methode_info,
        config=config_actuelle,
    )


# ═══════════════════════════════════════════════════════════════
# TOGGLE ACTIF / INACTIF
# ═══════════════════════════════════════════════════════════════

@dashboard_paiement_bp.route("/paiement/<method>/toggle", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def toggle(method):
    """Active ou désactive une méthode."""
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if not methode_est_valide(method):
        flash("Methode invalide.", "error")
        return redirect(url_for("dashboard_paiement.index"))

    actif_actuel = request.form.get("actif") == "1"
    nouveau_statut = not actif_actuel

    # Si on active, vérifier que la config existe
    if nouveau_statut:
        config = get_config_revendeur(profile["id"], method)
        if not config:
            flash("Configurez d'abord cette methode.", "warning")
            return redirect(url_for("dashboard_paiement.configurer", method=method))

    ok = toggle_config_actif(profile["id"], method, nouveau_statut)

    if ok:
        etat = "activee" if nouveau_statut else "desactivee"
        flash(f"Methode {etat}.", "success")
    else:
        flash("Erreur lors du changement de statut.", "error")

    return redirect(url_for("dashboard_paiement.index"))


# ═══════════════════════════════════════════════════════════════
# SUPPRESSION D'UNE CONFIG
# ═══════════════════════════════════════════════════════════════

@dashboard_paiement_bp.route("/paiement/<method>/supprimer", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def supprimer(method):
    """Supprime la config d'une méthode."""
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if not methode_est_valide(method):
        flash("Methode invalide.", "error")
        return redirect(url_for("dashboard_paiement.index"))

    ok = supprimer_config_revendeur(profile["id"], method)

    if ok:
        flash("Configuration supprimee.", "success")
    else:
        flash("Erreur lors de la suppression.", "error")

    return redirect(url_for("dashboard_paiement.index"))