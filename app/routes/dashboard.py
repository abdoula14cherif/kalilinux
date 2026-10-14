"""
Dashboard revendeur — toutes les pages de l'espace revendeur.
"""
import logging
import re
import json
from datetime import datetime, timezone
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app.models.security import login_required
from app.models.database import (
    get_profile, update_profile, get_active_services,
    get_revendeur_prix_all, set_revendeur_prix, get_service_by_id,
    get_revendeur_clients_detail, get_revendeur_orders,
    get_revendeur_gains_total, slug_deja_pris,
    debit_balance, credit_balance, activer_revendeur,
    get_all_boutique_types, get_boutique_type, get_categories_par_type,
    get_produits_revendeur, create_produit_boutique, update_produit_boutique,
    delete_produit_boutique, get_produit_boutique,
    create_categorie, update_categorie, delete_categorie,
    get_abonnements_plans, get_fonctionnalites_premium
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


def _get_profile_ou_redirect(check_type=True):
    user_id = session.get("user_id")
    if not user_id:
        return None, redirect(url_for("auth.connexion"))
    profile = get_profile(user_id)
    if not profile:
        from app.models.security import clear_session
        clear_session()
        return None, redirect(url_for("auth.connexion"))

    if check_type and not profile.get("boutique_type"):
        if request.endpoint != "dashboard.choisir_type":
            return None, redirect(url_for("dashboard.choisir_type"))

    return profile, None


# ═══════════════════════════════════════════════════════════════
# CHOISIR TYPE
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/choisir-type", methods=["GET", "POST"])
@login_required
def choisir_type():
    profile, redir = _get_profile_ou_redirect(check_type=False)
    if redir:
        return redir

    if request.method == "POST":
        type_code = request.form.get("boutique_type", "").strip()
        type_obj = get_boutique_type(type_code)
        if not type_obj:
            flash("Type invalide.", "error")
            return redirect(url_for("dashboard.choisir_type"))

        update_profile(profile["id"], {
            "boutique_type": type_code,
            "boutique_type_choisi_le": datetime.now(timezone.utc).isoformat(),
        })
        flash(f"✅ Type de boutique choisi : {type_obj['nom']}", "success")
        return redirect(url_for("dashboard.index"))

    types_boutique = get_all_boutique_types()
    return render_template("dashboard/choisir_type.html",
                          profile=profile,
                          types_boutique=types_boutique)


# ═══════════════════════════════════════════════════════════════
# ACCUEIL
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/")
@login_required
def index():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    type_boutique = get_boutique_type(profile["boutique_type"]) or {}

    stats = {"nb_produits": 0, "nb_commandes": 0, "revenus": 0, "nb_clients": 0}

    if profile["boutique_type"] == "digital":
        mes_prix = get_revendeur_prix_all(profile["id"]) if profile.get("est_revendeur") else []
        stats["nb_produits"] = len(mes_prix)
    else:
        produits = get_produits_revendeur(profile["id"])
        stats["nb_produits"] = len(produits)
        stats["nb_actifs"] = sum(1 for p in produits if p.get("actif"))

    try:
        orders = get_revendeur_orders(profile["id"], limit=100)
        stats["nb_commandes"] = len(orders)
        stats["revenus"] = sum(o.get("prix_total", 0) or 0 for o in orders if o.get("statut") == "termine")
    except Exception:
        pass

    try:
        clients = get_revendeur_clients_detail(profile["id"])
        stats["nb_clients"] = len(clients)
    except Exception:
        pass

    return render_template("dashboard/index.html",
                          profile=profile,
                          type_boutique=type_boutique,
                          stats=stats)


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
    data = {}

    data["boutique_nom"] = request.form.get("boutique_nom", "").strip() or None
    data["boutique_slogan"] = request.form.get("boutique_slogan", "").strip() or None
    data["boutique_message_accueil"] = request.form.get("boutique_message_accueil", "").strip() or None
    data["boutique_a_propos"] = request.form.get("boutique_a_propos", "").strip() or None
    data["boutique_whatsapp"] = request.form.get("boutique_whatsapp", "").strip() or None
    data["boutique_email"] = request.form.get("boutique_email", "").strip() or None
    data["boutique_facebook"] = request.form.get("boutique_facebook", "").strip() or None
    data["boutique_instagram"] = request.form.get("boutique_instagram", "").strip() or None
    data["boutique_tiktok"] = request.form.get("boutique_tiktok", "").strip() or None
    data["boutique_telegram"] = request.form.get("boutique_telegram", "").strip() or None

    theme = request.form.get("boutique_theme", "bleu")
    if theme in THEMES:
        data["boutique_theme"] = theme
        data["boutique_couleur_principale"] = THEMES[theme][0]
        data["boutique_couleur_secondaire"] = THEMES[theme][1]

    data["boutique_afficher_prix"] = request.form.get("boutique_afficher_prix") == "on"
    data["boutique_whatsapp_flottant"] = request.form.get("boutique_whatsapp_flottant") == "on"
    data["boutique_badge_verifie"] = request.form.get("boutique_badge_verifie") == "on"
    data["boutique_slogan_anime"] = request.form.get("boutique_slogan_anime") == "on"

    type_grille = request.form.get("boutique_type_grille", "grille")
    if type_grille in ("grille", "cartes", "liste"):
        data["boutique_type_grille"] = type_grille

    try:
        spl = int(request.form.get("boutique_services_par_ligne", 3))
        if spl in (2, 3, 4):
            data["boutique_services_par_ligne"] = spl
    except Exception:
        pass

    try:
        note = float(request.form.get("boutique_note", 4.9))
        data["boutique_note"] = min(5, max(0, note))
    except Exception:
        pass
    try:
        nb_avis = int(request.form.get("boutique_nb_avis", 0))
        data["boutique_nb_avis"] = max(0, nb_avis)
    except Exception:
        pass

    sections = {}
    for key in ("stats", "avantages", "comment", "services", "apropos", "avis", "faq"):
        sections[key] = request.form.get(f"section_{key}") == "on"
    data["boutique_sections_affichees"] = sections

    logo_file = request.files.get("boutique_logo")
    if logo_file and logo_file.filename:
        try:
            logo_url = upload_image(logo_file, prefix="logo_")
            if logo_url:
                data["boutique_logo_url"] = logo_url
        except Exception as e:
            logger.error(f"Logo exception: {e}")

    banniere_file = request.files.get("boutique_banniere")
    if banniere_file and banniere_file.filename:
        try:
            banniere_url = upload_image(banniere_file, prefix="banniere_")
            if banniere_url:
                data["boutique_banniere_url"] = banniere_url
        except Exception as e:
            logger.error(f"Banniere exception: {e}")

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
# PUBLIER
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/publier")
@login_required
def publier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    types_boutique = get_all_boutique_types()
    etapes_ok = {
        "nom": bool(profile.get("boutique_nom")),
        "whatsapp": bool(profile.get("boutique_whatsapp")),
        "logo_ou_slogan": bool(profile.get("boutique_logo_url") or profile.get("boutique_slogan")),
    }
    return render_template("dashboard/publier.html",
                          profile=profile,
                          prix_activation=PRIX_ACTIVATION,
                          etapes_ok=etapes_ok,
                          types_boutique=types_boutique)


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
        flash(f"Solde insuffisant. Il vous faut {PRIX_ACTIVATION:,.0f} FCFA.", "error")
        return redirect(url_for("dashboard.publier"))

    slug = request.form.get("slug", "").strip().lower()
    if not slug or len(slug) < 3 or len(slug) > 30:
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard.publier"))
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,28}[a-z0-9]", slug):
        flash("Identifiant invalide.", "error")
        return redirect(url_for("dashboard.publier"))

    modele = request.form.get("modele", "")
    if modele not in ("marge", "commission"):
        flash("Choisissez un modele.", "error")
        return redirect(url_for("dashboard.publier"))

    if slug_deja_pris(slug):
        flash("Cet identifiant est deja pris.", "error")
        return redirect(url_for("dashboard.publier"))

    nouveau_solde = debit_balance(profile["id"], PRIX_ACTIVATION)
    if nouveau_solde is None:
        flash("Erreur de paiement.", "error")
        return redirect(url_for("dashboard.publier"))

    commission = 0.10 if modele == "commission" else 0.0
    ok = activer_revendeur(profile["id"], slug, modele, commission)

    if ok:
        update_profile(profile["id"], {
            "boutique_brouillon": False,
            "boutique_publiee": True,
            "boutique_publiee_le": datetime.now(timezone.utc).isoformat(),
        })
        flash(f"🎉 Felicitations ! Votre boutique est en ligne : /r/{slug}", "success")
        return redirect(url_for("dashboard.index"))
    else:
        credit_balance(profile["id"], PRIX_ACTIVATION)
        flash("Erreur d'activation. Rembourse.", "error")
        return redirect(url_for("dashboard.publier"))


# ═══════════════════════════════════════════════════════════════
# PRIX (Digital)
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
    return render_template("dashboard/prix.html", profile=profile, services=services, mes_prix=mes_prix)


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
        flash(f"Prix minimum : {service['prix_fcfa']} FCFA.", "error")
        return redirect(url_for("dashboard.prix"))
    ok = set_revendeur_prix(profile["id"], service_id, prix_fcfa)
    if ok:
        flash("Prix enregistre.", "success")
    else:
        flash("Erreur.", "error")
    return redirect(url_for("dashboard.prix"))


# ═══════════════════════════════════════════════════════════════
# PRODUITS (autres types)
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/produits")
@login_required
def produits():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    liste_produits = get_produits_revendeur(profile["id"])
    categories = get_categories_par_type(profile["boutique_type"])
    return render_template("dashboard/produits.html",
                          profile=profile,
                          produits=liste_produits,
                          categories=categories)


@dashboard_bp.route("/produits/ajouter", methods=["POST"])
@login_required
def produits_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    nom = request.form.get("nom", "").strip()
    description = request.form.get("description", "").strip()
    prix_str = request.form.get("prix", "0").strip()

    if not nom:
        flash("Le nom est requis.", "error")
        return redirect(url_for("dashboard.produits"))

    try:
        prix = float(prix_str)
    except Exception:
        prix = 0

    data = {
        "revendeur_id": profile["id"],
        "nom": nom,
        "description": description or None,
        "prix": prix,
        "actif": True,
    }

    categorie_id = request.form.get("categorie_id", "").strip()
    if categorie_id:
        try:
            data["categorie_id"] = int(categorie_id)
        except Exception:
            pass

    image_file = request.files.get("image")
    if image_file and image_file.filename:
        image_url = upload_image(image_file, prefix="produit_")
        if image_url:
            data["image_url"] = image_url

    stock_str = request.form.get("stock", "").strip()
    if stock_str:
        try:
            data["stock"] = int(stock_str)
        except Exception:
            pass

    result = create_produit_boutique(data)
    if result:
        flash(f"✅ Produit '{nom}' ajoute !", "success")
    else:
        flash("Erreur lors de l'ajout.", "error")

    return redirect(url_for("dashboard.produits"))


@dashboard_bp.route("/produits/modifier", methods=["POST"])
@login_required
def produits_modifier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    produit_id = request.form.get("produit_id", "")
    if not produit_id:
        flash("ID manquant.", "error")
        return redirect(url_for("dashboard.produits"))

    data = {}
    data["nom"] = request.form.get("nom", "").strip() or None
    data["description"] = request.form.get("description", "").strip() or None

    try:
        prix = float(request.form.get("prix", "0"))
        data["prix"] = prix
    except Exception:
        pass

    categorie_id = request.form.get("categorie_id", "").strip()
    if categorie_id:
        try:
            data["categorie_id"] = int(categorie_id)
        except Exception:
            pass

    stock_str = request.form.get("stock", "").strip()
    if stock_str:
        try:
            data["stock"] = int(stock_str)
        except Exception:
            pass

    image_file = request.files.get("image")
    if image_file and image_file.filename:
        image_url = upload_image(image_file, prefix="produit_")
        if image_url:
            data["image_url"] = image_url

    ok = update_produit_boutique(produit_id, data)
    if ok:
        flash("✅ Produit mis a jour.", "success")
    else:
        flash("Erreur.", "error")

    return redirect(url_for("dashboard.produits"))


@dashboard_bp.route("/produits/supprimer", methods=["POST"])
@login_required
def produits_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    produit_id = request.form.get("produit_id", "")
    if produit_id:
        ok = delete_produit_boutique(produit_id)
        if ok:
            flash("Produit supprime.", "success")
        else:
            flash("Erreur.", "error")

    return redirect(url_for("dashboard.produits"))


@dashboard_bp.route("/produits/toggle", methods=["POST"])
@login_required
def produits_toggle():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    produit_id = request.form.get("produit_id", "")
    actif = request.form.get("actif") == "1"
    if produit_id:
        update_produit_boutique(produit_id, {"actif": not actif})

    return redirect(url_for("dashboard.produits"))


# ═══════════════════════════════════════════════════════════════
# CATEGORIES
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/categories")
@login_required
def categories():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    categories_liste = get_categories_par_type(profile["boutique_type"])
    return render_template("dashboard/categories.html",
                          profile=profile,
                          categories=categories_liste)


@dashboard_bp.route("/categories/ajouter", methods=["POST"])
@login_required
def categories_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    nom = request.form.get("nom", "").strip()
    description = request.form.get("description", "").strip() or None

    if not nom:
        flash("Le nom est requis.", "error")
        return redirect(url_for("dashboard.categories"))

    result = create_categorie(profile["boutique_type"], nom, description)
    if result:
        flash(f"✅ Categorie '{nom}' creee !", "success")
    else:
        flash("Erreur lors de la creation.", "error")

    return redirect(url_for("dashboard.categories"))


@dashboard_bp.route("/categories/modifier", methods=["POST"])
@login_required
def categories_modifier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    cat_id = request.form.get("categorie_id", "")
    if not cat_id:
        flash("ID manquant.", "error")
        return redirect(url_for("dashboard.categories"))

    data = {
        "nom": request.form.get("nom", "").strip(),
        "description": request.form.get("description", "").strip() or None,
    }

    ok = update_categorie(cat_id, data)
    if ok:
        flash("✅ Categorie mise a jour.", "success")
    else:
        flash("Erreur.", "error")

    return redirect(url_for("dashboard.categories"))


@dashboard_bp.route("/categories/supprimer", methods=["POST"])
@login_required
def categories_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    cat_id = request.form.get("categorie_id", "")
    if cat_id:
        ok = delete_categorie(cat_id)
        if ok:
            flash("Categorie supprimee.", "success")
        else:
            flash("Erreur.", "error")

    return redirect(url_for("dashboard.categories"))


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
    return render_template("dashboard/clients.html", profile=profile, mes_clients=mes_clients)


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
    return render_template("dashboard/commandes.html", profile=profile, orders=orders)


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
    return render_template("dashboard/gains.html", profile=profile, gains_total=gains_total)


# ═══════════════════════════════════════════════════════════════
# PREMIUM
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/premium")
@login_required
def premium():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    features = get_fonctionnalites_premium()
    return render_template("dashboard/premium.html", profile=profile, features=features)


# ═══════════════════════════════════════════════════════════════
# ABONNEMENT
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/abonnement")
@login_required
def abonnement():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    plans = get_abonnements_plans()
    return render_template("dashboard/abonnement.html", profile=profile, plans=plans)


# ═══════════════════════════════════════════════════════════════
# PARAMETRES
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/parametres")
@login_required
def parametres():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    types_boutique = get_all_boutique_types()
    return render_template("dashboard/parametres.html",
                          profile=profile,
                          types_boutique=types_boutique)


# ═══════════════════════════════════════════════════════════════
# BANNIÈRES
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/bannieres")
@login_required
def bannieres():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    from app.models.database import get_bannieres_revendeur
    liste = get_bannieres_revendeur(profile["id"])
    return render_template("dashboard/bannieres.html", profile=profile, bannieres=liste)


@dashboard_bp.route("/bannieres/ajouter", methods=["POST"])
@login_required
def bannieres_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    titre = request.form.get("titre", "").strip() or None
    sous_titre = request.form.get("sous_titre", "").strip() or None
    lien = request.form.get("lien", "").strip() or None
    couleur_fond = request.form.get("couleur_fond", "#00BFFF")
    couleur_texte = request.form.get("couleur_texte", "#FFFFFF")

    image_file = request.files.get("image")
    if not image_file or not image_file.filename:
        flash("Une image est requise pour la banniere.", "error")
        return redirect(url_for("dashboard.bannieres"))

    image_url = upload_image(image_file, prefix="banniere_")
    if not image_url:
        flash("Erreur upload image.", "error")
        return redirect(url_for("dashboard.bannieres"))

    from app.models.database import create_banniere
    result = create_banniere({
        "revendeur_id": profile["id"],
        "titre": titre,
        "sous_titre": sous_titre,
        "image_url": image_url,
        "lien": lien,
        "couleur_fond": couleur_fond,
        "couleur_texte": couleur_texte,
        "actif": True,
    })

    if result:
        flash("✅ Banniere ajoutee !", "success")
    else:
        flash("Erreur lors de l'ajout.", "error")

    return redirect(url_for("dashboard.bannieres"))


@dashboard_bp.route("/bannieres/modifier", methods=["POST"])
@login_required
def bannieres_modifier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    banniere_id = request.form.get("banniere_id", "")
    if not banniere_id:
        flash("ID manquant.", "error")
        return redirect(url_for("dashboard.bannieres"))

    data = {
        "titre": request.form.get("titre", "").strip() or None,
        "sous_titre": request.form.get("sous_titre", "").strip() or None,
        "lien": request.form.get("lien", "").strip() or None,
        "couleur_fond": request.form.get("couleur_fond", "#00BFFF"),
        "couleur_texte": request.form.get("couleur_texte", "#FFFFFF"),
    }

    image_file = request.files.get("image")
    if image_file and image_file.filename:
        image_url = upload_image(image_file, prefix="banniere_")
        if image_url:
            data["image_url"] = image_url

    from app.models.database import update_banniere
    ok = update_banniere(banniere_id, data)
    if ok:
        flash("✅ Banniere mise a jour.", "success")
    else:
        flash("Erreur.", "error")

    return redirect(url_for("dashboard.bannieres"))


@dashboard_bp.route("/bannieres/supprimer", methods=["POST"])
@login_required
def bannieres_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    banniere_id = request.form.get("banniere_id", "")
    if banniere_id:
        from app.models.database import delete_banniere
        delete_banniere(banniere_id)
        flash("Banniere supprimee.", "success")
    return redirect(url_for("dashboard.bannieres"))


@dashboard_bp.route("/bannieres/toggle", methods=["POST"])
@login_required
def bannieres_toggle():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    banniere_id = request.form.get("banniere_id", "")
    actif = request.form.get("actif") == "1"
    if banniere_id:
        from app.models.database import update_banniere
        update_banniere(banniere_id, {"actif": not actif})
    return redirect(url_for("dashboard.bannieres"))


# ═══════════════════════════════════════════════════════════════
# ATTRIBUTS
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/attributs")
@login_required
def attributs():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    from app.models.database import get_attributs_revendeur
    liste = get_attributs_revendeur(profile["id"])
    return render_template("dashboard/attributs.html", profile=profile, attributs=liste)


@dashboard_bp.route("/attributs/ajouter", methods=["POST"])
@login_required
def attributs_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    nom = request.form.get("nom", "").strip()
    type_attr = request.form.get("type", "texte")
    valeurs_str = request.form.get("valeurs", "").strip()
    obligatoire = request.form.get("obligatoire") == "on"

    if not nom:
        flash("Le nom est requis.", "error")
        return redirect(url_for("dashboard.attributs"))

    # Convertir "S,M,L,XL" en liste
    valeurs = []
    if valeurs_str:
        valeurs = [v.strip() for v in valeurs_str.split(",") if v.strip()]

    from app.models.database import create_attribut
    result = create_attribut({
        "revendeur_id": profile["id"],
        "nom": nom,
        "type": type_attr,
        "valeurs": valeurs,
        "obligatoire": obligatoire,
        "actif": True,
    })

    if result:
        flash(f"✅ Attribut '{nom}' cree !", "success")
    else:
        flash("Erreur lors de la creation.", "error")

    return redirect(url_for("dashboard.attributs"))


@dashboard_bp.route("/attributs/modifier", methods=["POST"])
@login_required
def attributs_modifier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    attribut_id = request.form.get("attribut_id", "")
    if not attribut_id:
        flash("ID manquant.", "error")
        return redirect(url_for("dashboard.attributs"))

    nom = request.form.get("nom", "").strip()
    type_attr = request.form.get("type", "texte")
    valeurs_str = request.form.get("valeurs", "").strip()
    obligatoire = request.form.get("obligatoire") == "on"

    valeurs = []
    if valeurs_str:
        valeurs = [v.strip() for v in valeurs_str.split(",") if v.strip()]

    from app.models.database import update_attribut
    ok = update_attribut(attribut_id, {
        "nom": nom,
        "type": type_attr,
        "valeurs": valeurs,
        "obligatoire": obligatoire,
    })

    if ok:
        flash("✅ Attribut mis a jour.", "success")
    else:
        flash("Erreur.", "error")

    return redirect(url_for("dashboard.attributs"))


@dashboard_bp.route("/attributs/supprimer", methods=["POST"])
@login_required
def attributs_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    attribut_id = request.form.get("attribut_id", "")
    if attribut_id:
        from app.models.database import delete_attribut
        delete_attribut(attribut_id)
        flash("Attribut supprime.", "success")
    return redirect(url_for("dashboard.attributs"))


@dashboard_bp.route("/attributs/toggle", methods=["POST"])
@login_required
def attributs_toggle():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    attribut_id = request.form.get("attribut_id", "")
    actif = request.form.get("actif") == "1"
    if attribut_id:
        from app.models.database import update_attribut
        update_attribut(attribut_id, {"actif": not actif})
    return redirect(url_for("dashboard.attributs"))

# ═══════════════════════════════════════════════════════════════
# CONTACTS (réutilise clients existants)
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/contacts")
@login_required
def contacts():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    mes_contacts = []
    try:
        mes_contacts = get_revendeur_clients_detail(profile["id"])
    except Exception as e:
        logger.error(f"contacts load: {e}")
    return render_template("dashboard/contacts.html", profile=profile, contacts=mes_contacts)


# ═══════════════════════════════════════════════════════════════
# REVIEWS (avis)
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/reviews")
@login_required
def reviews():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    from app.models.database import get_avis_revendeur
    liste = get_avis_revendeur(profile["id"])
    return render_template("dashboard/reviews.html", profile=profile, avis=liste)


@dashboard_bp.route("/reviews/ajouter", methods=["POST"])
@login_required
def reviews_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    client_nom = request.form.get("client_nom", "").strip()
    client_email = request.form.get("client_email", "").strip() or None
    commentaire = request.form.get("commentaire", "").strip() or None

    try:
        note = int(request.form.get("note", 5))
        note = max(1, min(5, note))
    except Exception:
        note = 5

    if not client_nom:
        flash("Le nom du client est requis.", "error")
        return redirect(url_for("dashboard.reviews"))

    from app.models.database import create_avis
    result = create_avis({
        "revendeur_id": profile["id"],
        "client_nom": client_nom,
        "client_email": client_email,
        "note": note,
        "commentaire": commentaire,
        "approuve": True,
    })

    if result:
        flash(f"✅ Avis de {client_nom} ajoute !", "success")
    else:
        flash("Erreur lors de l'ajout.", "error")

    return redirect(url_for("dashboard.reviews"))


@dashboard_bp.route("/reviews/approuver", methods=["POST"])
@login_required
def reviews_approuver():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    avis_id = request.form.get("avis_id", "")
    approuve = request.form.get("approuve") == "1"
    if avis_id:
        from app.models.database import update_avis
        update_avis(avis_id, {"approuve": not approuve})
    return redirect(url_for("dashboard.reviews"))


@dashboard_bp.route("/reviews/supprimer", methods=["POST"])
@login_required
def reviews_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    avis_id = request.form.get("avis_id", "")
    if avis_id:
        from app.models.database import delete_avis
        delete_avis(avis_id)
        flash("Avis supprime.", "success")
    return redirect(url_for("dashboard.reviews"))


# ═══════════════════════════════════════════════════════════════
# COUPONS
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/coupons")
@login_required
def coupons():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    from app.models.database import get_coupons_revendeur
    liste = get_coupons_revendeur(profile["id"])
    return render_template("dashboard/coupons.html", profile=profile, coupons=liste)


@dashboard_bp.route("/coupons/ajouter", methods=["POST"])
@login_required
def coupons_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    code = request.form.get("code", "").strip().upper()
    type_coupon = request.form.get("type", "pourcentage")
    date_expiration = request.form.get("date_expiration", "").strip() or None

    if not code:
        flash("Le code est requis.", "error")
        return redirect(url_for("dashboard.coupons"))

    try:
        valeur = float(request.form.get("valeur", 10))
        if valeur <= 0:
            raise ValueError
    except Exception:
        flash("Valeur invalide.", "error")
        return redirect(url_for("dashboard.coupons"))

    try:
        montant_min = float(request.form.get("montant_min", 0))
    except Exception:
        montant_min = 0

    try:
        max_util = int(request.form.get("max_utilisations", 100))
    except Exception:
        max_util = 100

    # Verifier que le code n'existe pas deja
    from app.models.database import get_coupon_by_code, create_coupon
    existant = get_coupon_by_code(profile["id"], code)
    if existant:
        flash(f"Le code {code} existe deja.", "error")
        return redirect(url_for("dashboard.coupons"))

    result = create_coupon({
        "revendeur_id": profile["id"],
        "code": code,
        "type": type_coupon,
        "valeur": valeur,
        "montant_min": montant_min,
        "max_utilisations": max_util,
        "date_expiration": date_expiration,
        "actif": True,
    })

    if result:
        flash(f"✅ Coupon {code} cree !", "success")
    else:
        flash("Erreur lors de la creation.", "error")

    return redirect(url_for("dashboard.coupons"))


@dashboard_bp.route("/coupons/toggle", methods=["POST"])
@login_required
def coupons_toggle():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    coupon_id = request.form.get("coupon_id", "")
    actif = request.form.get("actif") == "1"
    if coupon_id:
        from app.models.database import update_coupon
        update_coupon(coupon_id, {"actif": not actif})
    return redirect(url_for("dashboard.coupons"))


@dashboard_bp.route("/coupons/supprimer", methods=["POST"])
@login_required
def coupons_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    coupon_id = request.form.get("coupon_id", "")
    if coupon_id:
        from app.models.database import delete_coupon
        delete_coupon(coupon_id)
        flash("Coupon supprime.", "success")
    return redirect(url_for("dashboard.coupons"))

# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS (préférences)
# ═══════════════════════════════════════════════════════════════

@dashboard_bp.route("/notifications-prefs", methods=["GET", "POST"])
@login_required
def notifications_prefs():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if request.method == "POST":
        data = {
            "notif_nouvelle_commande": request.form.get("notif_nouvelle_commande") == "on",
            "notif_paiement_recu": request.form.get("notif_paiement_recu") == "on",
            "notif_nouvel_avis": request.form.get("notif_nouvel_avis") == "on",
            "notif_nouveau_client": request.form.get("notif_nouveau_client") == "on",
            "notif_resume_quotidien": request.form.get("notif_resume_quotidien") == "on",
            "notif_stock_bas": request.form.get("notif_stock_bas") == "on",
            "notif_email": request.form.get("notif_email", "").strip() or None,
        }
        ok = update_profile(profile["id"], data)
        if ok:
            flash("✅ Preferences mises a jour !", "success")
        else:
            flash("Erreur lors de la sauvegarde.", "error")
        return redirect(url_for("dashboard.notifications_prefs"))

    return render_template("dashboard/notifications_prefs.html", profile=profile)