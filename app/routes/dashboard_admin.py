"""
Dashboard admin — Gestion complète de la plateforme.
SÉCURITÉ : rate limits renforcés, protection auto-modification,
validation UUID, logs systématiques.
"""
import logging
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app import limiter
from app.models.security import login_required
from app.models.database import get_profile, get_all_revendeurs, update_profile
from app.models.fonctionnalites import (
    get_toutes_fonctionnalites, toggle_fonctionnalite,
    toggle_premium_fonctionnalite, activer_feature_revendeur,
    get_features_revendeur
)
from app.models.admin import (
    log_admin_action, get_admin_logs, get_stats_globales,
    get_tous_utilisateurs, bannir_utilisateur, debannir_utilisateur,
    promouvoir_admin, modifier_balance, modifier_abonnement,
    supprimer_utilisateur, modifier_fonctionnalite,
    creer_fonctionnalite, supprimer_fonctionnalite,
    creer_notification_globale, get_notifications_globales,
    toggle_notification_globale, supprimer_notification_globale,
    # ─── Credit Boost admin ───
    ajouter_credit_boost, deduire_credit_boost,
    get_transactions_credit_boost_admin,
    get_revendeurs_credit_faible,
    _valider_uuid,
)

logger = logging.getLogger(__name__)
dashboard_admin_bp = Blueprint("dashboard_admin", __name__)


def _require_admin():
    """Verifie que l'utilisateur connecte est admin."""
    user_id = session.get("user_id")
    if not user_id:
        return None, redirect(url_for("auth.connexion"))
    profile = get_profile(user_id)
    if not profile:
        from app.models.security import clear_session
        clear_session()
        return None, redirect(url_for("auth.connexion"))
    if not profile.get("est_admin"):
        # Log la tentative d'acces non autorise
        logger.warning(
            f"[SECURITE] Tentative acces admin refuse : user={user_id} "
            f"path={request.path}"
        )
        flash("Acces reserve aux administrateurs.", "error")
        return None, redirect(url_for("dashboard.index"))
    return profile, None


def _ip():
    """
    Recupere l'IP reelle du client en tenant compte du proxy.
    ATTENTION : ne PAS faire confiance au premier X-Forwarded-For
    si le proxy n'est pas configure pour le nettoyer.
    """
    # Priorite : header injecte par le reverse proxy de confiance (Vercel)
    # Vercel utilise x-real-ip et x-forwarded-for
    xri = request.headers.get("X-Real-IP")
    if xri:
        return xri.strip()[:45]

    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        # Vercel : le DERNIER est l'IP du proxy, l'AVANT-DERNIER est le client
        # En pratique on prend le premier (le plus a gauche = client reel)
        # car Vercel nettoie ce header
        return xff.split(",")[0].strip()[:45]

    return (request.remote_addr or "")[:45]


# ═══════════════════════════════════════════════════════════════
# DASHBOARD PRINCIPAL
# ═══════════════════════════════════════════════════════════════

@dashboard_admin_bp.route("/")
@login_required
def index():
    profile, redir = _require_admin()
    if redir:
        return redir

    stats = get_stats_globales()
    return render_template("dashboard/admin/index.html",
                          profile=profile,
                          stats=stats)


# ═══════════════════════════════════════════════════════════════
# FONCTIONNALITES
# ═══════════════════════════════════════════════════════════════

@dashboard_admin_bp.route("/fonctionnalites")
@login_required
def fonctionnalites():
    profile, redir = _require_admin()
    if redir:
        return redir

    features = get_toutes_fonctionnalites()
    return render_template("dashboard/admin/fonctionnalites.html",
                          profile=profile,
                          features=features)


@dashboard_admin_bp.route("/fonctionnalites/<code>/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def fonctionnalite_toggle(code):
    profile, redir = _require_admin()
    if redir:
        return redir

    # Sanitize code
    if not code or len(code) > 50:
        flash("Code invalide.", "error")
        return redirect(url_for("dashboard_admin.fonctionnalites"))
    code = code.strip().lower()[:50]

    actif = request.form.get("actif") == "1"
    ok = toggle_fonctionnalite(code, not actif)

    if ok:
        log_admin_action(profile["id"], f"toggle_feature_{'off' if actif else 'on'}",
                        cible_type="feature", details={"code": code}, ip=_ip())
        flash(f"Fonctionnalite '{code}' {'desactivee' if actif else 'activee'}.", "success")
    else:
        flash("Erreur lors du changement.", "error")
    return redirect(url_for("dashboard_admin.fonctionnalites"))


@dashboard_admin_bp.route("/fonctionnalites/<code>/premium", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def fonctionnalite_premium(code):
    profile, redir = _require_admin()
    if redir:
        return redir

    if not code or len(code) > 50:
        flash("Code invalide.", "error")
        return redirect(url_for("dashboard_admin.fonctionnalites"))
    code = code.strip().lower()[:50]

    est_premium = request.form.get("est_premium") == "1"
    ok = toggle_premium_fonctionnalite(code, not est_premium)

    if ok:
        log_admin_action(profile["id"], f"toggle_premium_{'off' if est_premium else 'on'}",
                        cible_type="feature", details={"code": code}, ip=_ip())
        flash(f"Fonctionnalite '{code}' marquee comme {'gratuite' if est_premium else 'premium'}.", "success")
    else:
        flash("Erreur lors du changement.", "error")
    return redirect(url_for("dashboard_admin.fonctionnalites"))


@dashboard_admin_bp.route("/fonctionnalites/<code>/modifier", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def fonctionnalite_modifier(code):
    profile, redir = _require_admin()
    if redir:
        return redir

    if not code or len(code) > 50:
        flash("Code invalide.", "error")
        return redirect(url_for("dashboard_admin.fonctionnalites"))
    code = code.strip().lower()[:50]

    data = {}
    for champ in ("nom", "description", "icone", "couleur"):
        val = request.form.get(champ, "").strip()
        if val:
            data[champ] = val[:200]

    try:
        ordre = int(request.form.get("ordre", 0))
        data["ordre"] = max(0, min(9999, ordre))
    except Exception:
        pass

    if not data:
        flash("Aucun champ à modifier.", "error")
        return redirect(url_for("dashboard_admin.fonctionnalites"))

    ok = modifier_fonctionnalite(code, data)
    if ok:
        log_admin_action(profile["id"], "modifier_feature",
                        cible_type="feature",
                        details={"code": code, "champs": list(data.keys())},
                        ip=_ip())
        flash(f"Fonctionnalite '{code}' mise a jour.", "success")
    else:
        flash("Erreur lors de la mise a jour.", "error")
    return redirect(url_for("dashboard_admin.fonctionnalites"))


@dashboard_admin_bp.route("/fonctionnalites/creer", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def fonctionnalite_creer():
    profile, redir = _require_admin()
    if redir:
        return redir

    code = request.form.get("code", "").strip().lower().replace(" ", "_")[:50]
    nom = request.form.get("nom", "").strip()[:100]
    if not code or not nom:
        flash("Code et nom obligatoires.", "error")
        return redirect(url_for("dashboard_admin.fonctionnalites"))

    data = {
        "code": code,
        "nom": nom,
        "description": request.form.get("description", "").strip()[:300] or None,
        "icone": request.form.get("icone", "fas fa-code").strip()[:50],
        "couleur": request.form.get("couleur", "#00BFFF").strip()[:20],
        "est_premium": request.form.get("est_premium") == "on",
        "actif": True,
        "ordre": max(0, min(9999, int(request.form.get("ordre", 99)))),
    }

    result = creer_fonctionnalite(data)
    if result:
        log_admin_action(profile["id"], "creer_feature", cible_type="feature",
                        details={"code": code}, ip=_ip())
        flash(f"Fonctionnalite '{code}' creee.", "success")
    else:
        flash("Erreur lors de la creation.", "error")
    return redirect(url_for("dashboard_admin.fonctionnalites"))


@dashboard_admin_bp.route("/fonctionnalites/<code>/supprimer", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def fonctionnalite_supprimer(code):
    profile, redir = _require_admin()
    if redir:
        return redir

    if not code or len(code) > 50:
        flash("Code invalide.", "error")
        return redirect(url_for("dashboard_admin.fonctionnalites"))
    code = code.strip().lower()[:50]

    ok = supprimer_fonctionnalite(code)
    if ok:
        log_admin_action(profile["id"], "supprimer_feature", cible_type="feature",
                        details={"code": code}, ip=_ip())
        flash(f"Fonctionnalite '{code}' supprimee.", "success")
    else:
        flash("Erreur lors de la suppression.", "error")
    return redirect(url_for("dashboard_admin.fonctionnalites"))


# ═══════════════════════════════════════════════════════════════
# REVENDEURS / UTILISATEURS
# ═══════════════════════════════════════════════════════════════

@dashboard_admin_bp.route("/revendeurs")
@login_required
def revendeurs():
    profile, redir = _require_admin()
    if redir:
        return redir

    search = request.args.get("search", "").strip()[:100]
    filtre = request.args.get("filtre", "").strip()

    utilisateurs = get_tous_utilisateurs(limit=500, search=search if search else None)

    # Filtres client-side (déjà chargés)
    if filtre == "credit_faible":
        utilisateurs = [u for u in utilisateurs
                        if float(u.get("credit_boost", 0) or 0) < 2000]
    elif filtre == "en_pause":
        utilisateurs = [u for u in utilisateurs
                        if u.get("est_revendeur") and u.get("boutique_active") is False]
    elif filtre == "credit_negatif":
        utilisateurs = [u for u in utilisateurs
                        if float(u.get("credit_boost", 0) or 0) < 0]

    return render_template("dashboard/admin/revendeurs.html",
                          profile=profile,
                          revendeurs=utilisateurs,
                          search=search,
                          filtre=filtre)


@dashboard_admin_bp.route("/revendeurs/<revendeur_id>/features")
@login_required
def revendeur_features(revendeur_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    revendeur_id = _valider_uuid(revendeur_id, "revendeur_id")
    if not revendeur_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    revendeur = get_profile(revendeur_id)
    if not revendeur:
        flash("Revendeur introuvable.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    toutes_features = get_toutes_fonctionnalites()
    features_actives = {f["feature_code"]: f.get("actif", False)
                        for f in get_features_revendeur(revendeur_id)}

    return render_template("dashboard/admin/revendeur_features.html",
                          profile=profile,
                          revendeur=revendeur,
                          features=toutes_features,
                          features_actives=features_actives)


@dashboard_admin_bp.route("/revendeurs/<revendeur_id>/features/<code>/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def revendeur_feature_toggle(revendeur_id, code):
    profile, redir = _require_admin()
    if redir:
        return redir

    revendeur_id = _valider_uuid(revendeur_id, "revendeur_id")
    if not revendeur_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    if not code or len(code) > 50:
        flash("Code invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeur_features",
                                revendeur_id=revendeur_id))
    code = code.strip().lower()[:50]

    actif_actuel = request.form.get("actif") == "1"
    ok = activer_feature_revendeur(revendeur_id, code, not actif_actuel)

    if ok:
        log_admin_action(profile["id"],
                        f"toggle_user_feature_{'off' if actif_actuel else 'on'}",
                        cible_type="user", cible_id=revendeur_id,
                        details={"code": code}, ip=_ip())
        flash(f"Feature '{code}' {'desactivee' if actif_actuel else 'activee'}.", "success")
    else:
        flash("Erreur.", "error")
    return redirect(url_for("dashboard_admin.revendeur_features",
                            revendeur_id=revendeur_id))


@dashboard_admin_bp.route("/revendeurs/<user_id>/bannir", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def revendeur_bannir(user_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    # Protection : ne peut pas se bannir soi-meme
    if user_id == profile["id"]:
        flash("Vous ne pouvez pas vous bannir vous-meme.", "error")
        logger.warning(f"[SECURITE] Tentative auto-ban admin {profile['id']}")
        return redirect(url_for("dashboard_admin.revendeurs"))

    # Protection : ne peut pas bannir un autre admin
    cible = get_profile(user_id)
    if cible and cible.get("est_admin"):
        flash("Impossible de bannir un autre administrateur.", "error")
        logger.warning(f"[SECURITE] Tentative ban admin {user_id} par {profile['id']}")
        return redirect(url_for("dashboard_admin.revendeurs"))

    raison = request.form.get("raison", "").strip()[:500] or None
    ok = bannir_utilisateur(user_id, raison)

    if ok:
        log_admin_action(profile["id"], "bannir_user", cible_type="user",
                        cible_id=user_id, details={"raison": raison}, ip=_ip())
        flash("Utilisateur banni.", "success")
    else:
        flash("Erreur.", "error")
    return redirect(url_for("dashboard_admin.revendeurs"))


@dashboard_admin_bp.route("/revendeurs/<user_id>/debannir", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def revendeur_debannir(user_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    ok = debannir_utilisateur(user_id)
    if ok:
        log_admin_action(profile["id"], "debannir_user", cible_type="user",
                        cible_id=user_id, ip=_ip())
        flash("Utilisateur debanni.", "success")
    else:
        flash("Erreur.", "error")
    return redirect(url_for("dashboard_admin.revendeurs"))


@dashboard_admin_bp.route("/revendeurs/<user_id>/promouvoir", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def revendeur_promouvoir(user_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    if user_id == profile["id"]:
        flash("Vous etes deja admin.", "info")
        return redirect(url_for("dashboard_admin.revendeurs"))

    est_admin_actuel = request.form.get("est_admin") == "1"
    ok = promouvoir_admin(user_id, not est_admin_actuel)

    if ok:
        log_admin_action(profile["id"],
                        f"toggle_admin_{'off' if est_admin_actuel else 'on'}",
                        cible_type="user", cible_id=user_id, ip=_ip())
        flash(f"Utilisateur {'retrograde' if est_admin_actuel else 'promu admin'}.", "success")
    else:
        flash("Erreur.", "error")
    return redirect(url_for("dashboard_admin.revendeurs"))


@dashboard_admin_bp.route("/revendeurs/<user_id>/balance", methods=["POST"])
@login_required
@limiter.limit("10 per hour")  # Renforce : action critique
def revendeur_balance(user_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    if user_id == profile["id"]:
        flash("Vous ne pouvez pas modifier votre propre solde.", "error")
        logger.warning(f"[SECURITE] Tentative auto-modif balance admin {profile['id']}")
        return redirect(url_for("dashboard_admin.revendeurs"))

    montant_form = request.form.get("balance", "").strip()
    ok, err = modifier_balance(user_id, montant_form)

    if ok:
        log_admin_action(profile["id"], "modifier_balance", cible_type="user",
                        cible_id=user_id, details={"nouveau": montant_form}, ip=_ip())
        flash(f"Solde mis à jour : {float(montant_form):,.0f} FCFA", "success")
    else:
        flash(f"Erreur : {err}", "error")
    return redirect(url_for("dashboard_admin.revendeurs"))


@dashboard_admin_bp.route("/revendeurs/<user_id>/abonnement", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def revendeur_abonnement(user_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    niveau = request.form.get("niveau", "gratuit")
    ok = modifier_abonnement(user_id, niveau)
    if ok:
        log_admin_action(profile["id"], "modifier_abonnement", cible_type="user",
                        cible_id=user_id, details={"niveau": niveau}, ip=_ip())
        flash(f"Abonnement changé en '{niveau}'.", "success")
    else:
        flash("Erreur.", "error")
    return redirect(url_for("dashboard_admin.revendeurs"))


@dashboard_admin_bp.route("/revendeurs/<user_id>/supprimer", methods=["POST"])
@login_required
@limiter.limit("5 per hour")  # TRES restrictif
def revendeur_supprimer(user_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    if user_id == profile["id"]:
        flash("Vous ne pouvez pas vous supprimer vous-meme.", "error")
        logger.warning(f"[SECURITE] Tentative auto-suppression admin {profile['id']}")
        return redirect(url_for("dashboard_admin.revendeurs"))

    # Ne peut pas supprimer un autre admin
    cible = get_profile(user_id)
    if cible and cible.get("est_admin"):
        flash("Impossible de supprimer un autre administrateur.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    confirm = request.form.get("confirm", "").strip()
    if confirm != "SUPPRIMER":
        flash("Tapez 'SUPPRIMER' pour confirmer.", "error")
        return redirect(url_for("dashboard_admin.revendeurs"))

    ok = supprimer_utilisateur(user_id)
    if ok:
        log_admin_action(profile["id"], "supprimer_user", cible_type="user",
                        cible_id=user_id, ip=_ip())
        flash("Utilisateur supprime definitivement.", "success")
    else:
        flash("Erreur.", "error")
    return redirect(url_for("dashboard_admin.revendeurs"))


# ═══════════════════════════════════════════════════════════════
# CREDIT BOOST — GESTION ADMIN
# ═══════════════════════════════════════════════════════════════

@dashboard_admin_bp.route("/credit-boost")
@login_required
def credit_boost():
    """Vue globale de tous les Credit Boost."""
    profile, redir = _require_admin()
    if redir:
        return redir

    # Stats
    stats = get_stats_globales()

    # Revendeurs avec credit faible
    revendeurs_faibles = get_revendeurs_credit_faible(seuil=2000, limit=100)

    # Dernieres transactions
    transactions = get_transactions_credit_boost_admin(limit=100)

    return render_template("dashboard/admin/credit_boost.html",
                          profile=profile,
                          stats=stats,
                          revendeurs_faibles=revendeurs_faibles,
                          transactions=transactions)


@dashboard_admin_bp.route("/revendeurs/<user_id>/credit")
@login_required
def revendeur_credit(user_id):
    """Detail du Credit Boost d'un revendeur."""
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    revendeur = get_profile(user_id)
    if not revendeur:
        flash("Revendeur introuvable.", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    transactions = get_transactions_credit_boost_admin(user_id=user_id, limit=100)

    return render_template("dashboard/admin/revendeur_credit.html",
                          profile=profile,
                          revendeur=revendeur,
                          transactions=transactions)


@dashboard_admin_bp.route("/revendeurs/<user_id>/credit/ajouter", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def revendeur_credit_ajouter(user_id):
    """Ajoute du Credit Boost manuellement."""
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    montant = request.form.get("montant", "").strip()
    raison = request.form.get("raison", "").strip()

    ok, err = ajouter_credit_boost(user_id, montant, raison)

    if ok:
        log_admin_action(profile["id"], "credit_boost_ajout",
                        cible_type="user", cible_id=user_id,
                        details={"montant": montant, "raison": raison[:100]},
                        ip=_ip())
        flash(f"Credit Boost ajoute : +{float(montant):,.0f} FCFA", "success")
    else:
        flash(f"Erreur : {err}", "error")

    return redirect(url_for("dashboard_admin.revendeur_credit", user_id=user_id))


@dashboard_admin_bp.route("/revendeurs/<user_id>/credit/deduire", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def revendeur_credit_deduire(user_id):
    """Deduit du Credit Boost manuellement."""
    profile, redir = _require_admin()
    if redir:
        return redir

    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.credit_boost"))

    montant = request.form.get("montant", "").strip()
    raison = request.form.get("raison", "").strip()

    ok, err = deduire_credit_boost(user_id, montant, raison)

    if ok:
        log_admin_action(profile["id"], "credit_boost_deduction",
                        cible_type="user", cible_id=user_id,
                        details={"montant": montant, "raison": raison[:100]},
                        ip=_ip())
        flash(f"Credit Boost deduit : -{float(montant):,.0f} FCFA", "warning")
    else:
        flash(f"Erreur : {err}", "error")

    return redirect(url_for("dashboard_admin.revendeur_credit", user_id=user_id))


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS GLOBALES
# ═══════════════════════════════════════════════════════════════

@dashboard_admin_bp.route("/notifications")
@login_required
def notifications():
    profile, redir = _require_admin()
    if redir:
        return redir

    notifs = get_notifications_globales(actif_only=False)
    return render_template("dashboard/admin/notifications.html",
                          profile=profile,
                          notifications=notifs)


@dashboard_admin_bp.route("/notifications/creer", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def notification_creer():
    profile, redir = _require_admin()
    if redir:
        return redir

    titre = request.form.get("titre", "").strip()[:100]
    message = request.form.get("message", "").strip()[:500]
    type_notif = request.form.get("type", "info")

    if not titre or not message:
        flash("Titre et message obligatoires.", "error")
        return redirect(url_for("dashboard_admin.notifications"))

    if type_notif not in ("info", "success", "warning", "danger"):
        type_notif = "info"

    result = creer_notification_globale(titre, message, type_notif)
    if result:
        log_admin_action(profile["id"], "creer_notification",
                        details={"titre": titre}, ip=_ip())
        flash("Notification envoyee a tous les revendeurs.", "success")
    else:
        flash("Erreur.", "error")
    return redirect(url_for("dashboard_admin.notifications"))


@dashboard_admin_bp.route("/notifications/<notif_id>/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def notification_toggle(notif_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    notif_id = _valider_uuid(notif_id, "notif_id")
    if not notif_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.notifications"))

    actif = request.form.get("actif") == "1"
    toggle_notification_globale(notif_id, not actif)
    flash("Notification mise a jour.", "success")
    return redirect(url_for("dashboard_admin.notifications"))


@dashboard_admin_bp.route("/notifications/<notif_id>/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def notification_supprimer(notif_id):
    profile, redir = _require_admin()
    if redir:
        return redir

    notif_id = _valider_uuid(notif_id, "notif_id")
    if not notif_id:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard_admin.notifications"))

    supprimer_notification_globale(notif_id)
    log_admin_action(profile["id"], "supprimer_notification",
                    cible_type="notification", cible_id=notif_id, ip=_ip())
    flash("Notification supprimee.", "success")
    return redirect(url_for("dashboard_admin.notifications"))


# ═══════════════════════════════════════════════════════════════
# LOGS
# ═══════════════════════════════════════════════════════════════

@dashboard_admin_bp.route("/logs")
@login_required
def logs():
    profile, redir = _require_admin()
    if redir:
        return redir

    logs_list = get_admin_logs(limit=200)
    return render_template("dashboard/admin/logs.html",
                          profile=profile,
                          logs=logs_list)