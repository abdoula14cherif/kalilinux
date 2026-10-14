"""
Dashboard revendeur — routes principales (boutique, produits, bannières, catégories, attributs, prix).
"""
import logging
import re
from datetime import datetime, timezone
from flask import Blueprint, render_template, session, redirect, url_for, request, flash
from app import limiter
from app.models.security import login_required
from app.models.database import (
    get_profile, update_profile, get_active_services,
    get_revendeur_prix_all, set_revendeur_prix, get_service_by_id,
    slug_deja_pris,
    debit_balance, credit_balance, activer_revendeur,
    get_all_boutique_types, get_boutique_type, get_categories_par_type,
    get_produits_revendeur, create_produit_boutique, update_produit_boutique,
    delete_produit_boutique,
    create_categorie, update_categorie, delete_categorie,
    get_bannieres_revendeur, create_banniere, update_banniere, delete_banniere,
    get_attributs_revendeur, create_attribut, update_attribut, delete_attribut,
    get_revendeur_clients_detail, get_revendeur_orders
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
        flash("Votre session a expire. Reconnectez-vous.", "warning")
        return None, redirect(url_for("auth.connexion"))

    if check_type and not profile.get("boutique_type"):
        if request.endpoint != "dashboard.choisir_type":
            flash("Choisissez d'abord un type de boutique pour continuer.", "info")
            return None, redirect(url_for("dashboard.choisir_type"))

    return profile, None


def _verifier_propriete(table, item_id, revendeur_id):
    try:
        if not item_id or not revendeur_id:
            return False
        from app.models.database import _url, _headers
        import requests
        r = requests.get(
            _url(f"{table}?id=eq.{item_id}&revendeur_id=eq.{revendeur_id}&limit=1"),
            headers=_headers(True),
            timeout=10
        )
        if r.status_code >= 300:
            return False
        data = r.json()
        return isinstance(data, list) and len(data) > 0
    except Exception as e:
        logger.error(f"_verifier_propriete {table}: {type(e).__name__}")
        return False


def _verifier_categorie_revendeur(cat_id, revendeur_id):
    try:
        if not cat_id or not revendeur_id:
            return False
        produits = get_produits_revendeur(revendeur_id)
        for p in produits:
            if str(p.get("categorie_id")) == str(cat_id):
                return True
        return False
    except Exception as e:
        logger.error(f"_verifier_categorie_revendeur: {type(e).__name__}")
        return False


@dashboard_bp.route("/choisir-type", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per hour")
def choisir_type():
    profile, redir = _get_profile_ou_redirect(check_type=False)
    if redir:
        return redir

    if request.method == "POST":
        type_code = request.form.get("boutique_type", "").strip()
        type_obj = get_boutique_type(type_code)
        if not type_obj:
            flash("Type de boutique invalide. Reessayez.", "error")
            return redirect(url_for("dashboard.choisir_type"))

        old_type = profile.get("boutique_type")
        update_profile(profile["id"], {
            "boutique_type": type_code,
            "boutique_type_choisi_le": datetime.now(timezone.utc).isoformat(),
        })

        if old_type and old_type != type_code:
            flash(f"Type de boutique change : {type_obj['nom']}", "success")
        else:
            flash(f"Type de boutique choisi : {type_obj['nom']}", "success")

        return redirect(url_for("dashboard.index"))

    types_boutique = get_all_boutique_types()
    return render_template("dashboard/choisir_type.html",
                          profile=profile,
                          types_boutique=types_boutique)


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


@dashboard_bp.route("/boutique")
@login_required
def boutique():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    return render_template("dashboard/boutique.html", profile=profile, themes=THEMES)


@dashboard_bp.route("/boutique/enregistrer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def boutique_enregistrer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    user_id = profile["id"]
    data = {}

    data["boutique_nom"] = request.form.get("boutique_nom", "").strip()[:60] or None
    data["boutique_slogan"] = request.form.get("boutique_slogan", "").strip()[:100] or None
    data["boutique_message_accueil"] = request.form.get("boutique_message_accueil", "").strip()[:300] or None
    data["boutique_a_propos"] = request.form.get("boutique_a_propos", "").strip()[:1000] or None
    data["boutique_whatsapp"] = request.form.get("boutique_whatsapp", "").strip()[:30] or None
    data["boutique_email"] = request.form.get("boutique_email", "").strip()[:150] or None
    data["boutique_facebook"] = request.form.get("boutique_facebook", "").strip()[:300] or None
    data["boutique_instagram"] = request.form.get("boutique_instagram", "").strip()[:300] or None
    data["boutique_tiktok"] = request.form.get("boutique_tiktok", "").strip()[:300] or None
    data["boutique_telegram"] = request.form.get("boutique_telegram", "").strip()[:300] or None

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
        data["boutique_nb_avis"] = max(0, min(99999, nb_avis))
    except Exception:
        pass

    sections = {}
    for key in ("stats", "avantages", "comment", "services", "apropos", "avis", "faq"):
        sections[key] = request.form.get(f"section_{key}") == "on"
    data["boutique_sections_affichees"] = sections

    logo_file = request.files.get("boutique_logo")
    if logo_file and logo_file.filename:
        logo_url = upload_image(logo_file, prefix="logo_")
        if logo_url:
            data["boutique_logo_url"] = logo_url
            flash("Logo uploade !", "success")
        else:
            flash("Erreur upload logo. Verifiez le bucket Supabase.", "warning")

    banniere_file = request.files.get("boutique_banniere")
    if banniere_file and banniere_file.filename:
        banniere_url = upload_image(banniere_file, prefix="banniere_")
        if banniere_url:
            data["boutique_banniere_url"] = banniere_url
            flash("Banniere uploadee !", "success")
        else:
            flash("Erreur upload banniere.", "warning")

    ok = update_profile(user_id, data)
    if ok:
        flash("Boutique mise a jour avec succes !", "success")
    else:
        flash("Erreur lors de la sauvegarde. Reessayez.", "error")

    return redirect(url_for("dashboard.boutique"))


@dashboard_bp.route("/boutique/supprimer-image", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
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
    else:
        flash("Action invalide.", "error")

    return redirect(url_for("dashboard.boutique"))


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
@limiter.limit("5 per hour")
def publier_activer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    if profile.get("est_revendeur"):
        flash("Votre boutique est deja publiee.", "info")
        return redirect(url_for("dashboard.index"))

    balance = profile.get("balance", 0) or 0
    if balance < PRIX_ACTIVATION:
        flash(f"Solde insuffisant. Il vous faut {PRIX_ACTIVATION:,.0f} FCFA (solde actuel : {balance:,.0f} FCFA).", "error")
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
        flash("Choisissez un modele de gains.", "error")
        return redirect(url_for("dashboard.publier"))

    if slug_deja_pris(slug):
        flash(f"L'identifiant '{slug}' est deja pris. Choisissez-en un autre.", "error")
        return redirect(url_for("dashboard.publier"))

    nouveau_solde = debit_balance(profile["id"], PRIX_ACTIVATION)
    if nouveau_solde is None:
        flash("Erreur de paiement. Verifiez votre solde.", "error")
        return redirect(url_for("dashboard.publier"))

    commission = 0.10 if modele == "commission" else 0.0
    ok = activer_revendeur(profile["id"], slug, modele, commission)

    if ok:
        update_profile(profile["id"], {
            "boutique_brouillon": False,
            "boutique_publiee": True,
            "boutique_publiee_le": datetime.now(timezone.utc).isoformat(),
        })
        flash(f"Felicitations ! Votre boutique est en ligne : /r/{slug}", "success")
        return redirect(url_for("dashboard.index"))
    else:
        credit_balance(profile["id"], PRIX_ACTIVATION)
        flash("Erreur lors de l'activation. Vous avez ete rembourse.", "error")
        return redirect(url_for("dashboard.publier"))



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
        logger.error(f"prix load: {type(e).__name__}")
    return render_template("dashboard/prix.html", profile=profile, services=services, mes_prix=mes_prix)


@dashboard_bp.route("/prix/enregistrer", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def prix_enregistrer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    service_id = request.form.get("service_id", "")
    prix_str = request.form.get("prix_fcfa", "").strip()

    try:
        service_id = int(service_id)
        prix_fcfa = float(prix_str)
        if prix_fcfa <= 0 or prix_fcfa > 100000000:
            raise ValueError
    except Exception:
        flash("Valeurs invalides. Verifiez le prix.", "error")
        return redirect(url_for("dashboard.prix"))

    service = get_service_by_id(service_id)
    if not service:
        flash("Service introuvable.", "error")
        return redirect(url_for("dashboard.prix"))

    if prix_fcfa < float(service["prix_fcfa"]):
        flash(f"Le prix minimum est {service['prix_fcfa']} FCFA.", "error")
        return redirect(url_for("dashboard.prix"))

    ok = set_revendeur_prix(profile["id"], service_id, prix_fcfa)
    if ok:
        flash("Prix enregistre avec succes !", "success")
    else:
        flash("Erreur lors de l'enregistrement.", "error")
    return redirect(url_for("dashboard.prix"))


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
@limiter.limit("30 per hour")
def produits_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    nom = request.form.get("nom", "").strip()[:100]
    description = request.form.get("description", "").strip()[:1000]
    prix_str = request.form.get("prix", "0").strip()

    if not nom:
        flash("Le nom du produit est obligatoire.", "error")
        return redirect(url_for("dashboard.produits"))

    try:
        prix = float(prix_str)
        if prix < 0 or prix > 100000000:
            prix = 0
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
        else:
            flash("Erreur upload image. Le produit sera cree sans image.", "warning")

    stock_str = request.form.get("stock", "").strip()
    if stock_str:
        try:
            data["stock"] = int(stock_str)
        except Exception:
            pass

    result = create_produit_boutique(data)
    if result:
        flash(f"Produit '{nom}' ajoute avec succes !", "success")
    else:
        flash("Erreur lors de l'ajout du produit.", "error")

    return redirect(url_for("dashboard.produits"))


@dashboard_bp.route("/produits/modifier", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def produits_modifier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    produit_id = request.form.get("produit_id", "")
    if not produit_id:
        flash("ID produit manquant.", "error")
        return redirect(url_for("dashboard.produits"))

    if not _verifier_propriete("boutique_produits", produit_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative modif produit {produit_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard.produits"))

    data = {}
    nom = request.form.get("nom", "").strip()[:100]
    if nom:
        data["nom"] = nom
    data["description"] = request.form.get("description", "").strip()[:1000] or None

    try:
        prix = float(request.form.get("prix", "0"))
        if 0 <= prix <= 100000000:
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
        flash("Produit mis a jour.", "success")
    else:
        flash("Erreur lors de la mise a jour.", "error")

    return redirect(url_for("dashboard.produits"))


@dashboard_bp.route("/produits/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def produits_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    produit_id = request.form.get("produit_id", "")
    if not produit_id:
        flash("ID produit manquant.", "error")
        return redirect(url_for("dashboard.produits"))

    if not _verifier_propriete("boutique_produits", produit_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative suppression produit {produit_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard.produits"))

    ok = delete_produit_boutique(produit_id)
    if ok:
        flash("Produit supprime.", "success")
    else:
        flash("Erreur lors de la suppression.", "error")

    return redirect(url_for("dashboard.produits"))


@dashboard_bp.route("/produits/toggle", methods=["POST"])
@login_required
@limiter.limit("120 per hour")
def produits_toggle():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    produit_id = request.form.get("produit_id", "")
    actif = request.form.get("actif") == "1"

    if not produit_id:
        flash("ID produit manquant.", "error")
        return redirect(url_for("dashboard.produits"))

    if not _verifier_propriete("boutique_produits", produit_id, profile["id"]):
        flash("Action non autorisee.", "error")
        return redirect(url_for("dashboard.produits"))

    update_produit_boutique(produit_id, {"actif": not actif})
    flash(f"Produit {'desactive' if actif else 'active'}.", "success")
    return redirect(url_for("dashboard.produits"))



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
@limiter.limit("30 per hour")
def categories_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    nom = request.form.get("nom", "").strip()[:60]
    description = request.form.get("description", "").strip()[:300] or None

    if not nom:
        flash("Le nom de la categorie est obligatoire.", "error")
        return redirect(url_for("dashboard.categories"))

    result = create_categorie(profile["boutique_type"], nom, description)
    if result:
        flash(f"Categorie '{nom}' creee avec succes !", "success")
    else:
        flash("Erreur lors de la creation de la categorie.", "error")

    return redirect(url_for("dashboard.categories"))


@dashboard_bp.route("/categories/modifier", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def categories_modifier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    cat_id = request.form.get("categorie_id", "")
    if not cat_id:
        flash("ID categorie manquant.", "error")
        return redirect(url_for("dashboard.categories"))

    if not _verifier_categorie_revendeur(cat_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative modif categorie {cat_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard.categories"))

    data = {
        "nom": request.form.get("nom", "").strip()[:60],
        "description": request.form.get("description", "").strip()[:300] or None,
    }

    ok = update_categorie(cat_id, data)
    if ok:
        flash("Categorie mise a jour.", "success")
    else:
        flash("Erreur lors de la mise a jour.", "error")

    return redirect(url_for("dashboard.categories"))


@dashboard_bp.route("/categories/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def categories_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    cat_id = request.form.get("categorie_id", "")
    if not cat_id:
        flash("ID categorie manquant.", "error")
        return redirect(url_for("dashboard.categories"))

    if not _verifier_categorie_revendeur(cat_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative suppression categorie {cat_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard.categories"))

    ok = delete_categorie(cat_id)
    if ok:
        flash("Categorie supprimee.", "success")
    else:
        flash("Erreur lors de la suppression.", "error")

    return redirect(url_for("dashboard.categories"))


@dashboard_bp.route("/bannieres")
@login_required
def bannieres():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    liste = get_bannieres_revendeur(profile["id"])
    return render_template("dashboard/bannieres.html", profile=profile, bannieres=liste)


@dashboard_bp.route("/bannieres/ajouter", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def bannieres_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    titre = request.form.get("titre", "").strip()[:80] or None
    sous_titre = request.form.get("sous_titre", "").strip()[:120] or None
    lien = request.form.get("lien", "").strip()[:500] or None

    if lien and not lien.startswith(("http://", "https://")):
        lien = None

    image_file = request.files.get("image")
    if not image_file or not image_file.filename:
        flash("Une image est obligatoire pour la banniere.", "error")
        return redirect(url_for("dashboard.bannieres"))

    image_url = upload_image(image_file, prefix="banniere_")
    if not image_url:
        flash("Erreur upload image. Verifiez le bucket Supabase.", "error")
        return redirect(url_for("dashboard.bannieres"))

    result = create_banniere({
        "revendeur_id": profile["id"],
        "titre": titre,
        "sous_titre": sous_titre,
        "image_url": image_url,
        "lien": lien,
        "actif": True,
    })

    if result:
        flash("Banniere ajoutee avec succes !", "success")
    else:
        flash("Erreur lors de l'ajout de la banniere.", "error")

    return redirect(url_for("dashboard.bannieres"))


@dashboard_bp.route("/bannieres/modifier", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def bannieres_modifier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    banniere_id = request.form.get("banniere_id", "")
    if not banniere_id:
        flash("ID banniere manquant.", "error")
        return redirect(url_for("dashboard.bannieres"))

    if not _verifier_propriete("boutique_bannieres", banniere_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative modif banniere {banniere_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard.bannieres"))

    lien = request.form.get("lien", "").strip()[:500] or None
    if lien and not lien.startswith(("http://", "https://")):
        lien = None

    data = {
        "titre": request.form.get("titre", "").strip()[:80] or None,
        "sous_titre": request.form.get("sous_titre", "").strip()[:120] or None,
        "lien": lien,
    }

    image_file = request.files.get("image")
    if image_file and image_file.filename:
        image_url = upload_image(image_file, prefix="banniere_")
        if image_url:
            data["image_url"] = image_url

    ok = update_banniere(banniere_id, data)
    if ok:
        flash("Banniere mise a jour.", "success")
    else:
        flash("Erreur lors de la mise a jour.", "error")

    return redirect(url_for("dashboard.bannieres"))


@dashboard_bp.route("/bannieres/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def bannieres_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    banniere_id = request.form.get("banniere_id", "")
    if not banniere_id:
        flash("ID banniere manquant.", "error")
        return redirect(url_for("dashboard.bannieres"))

    if not _verifier_propriete("boutique_bannieres", banniere_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative suppression banniere {banniere_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard.bannieres"))

    delete_banniere(banniere_id)
    flash("Banniere supprimee.", "success")
    return redirect(url_for("dashboard.bannieres"))


@dashboard_bp.route("/bannieres/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def bannieres_toggle():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    banniere_id = request.form.get("banniere_id", "")
    actif = request.form.get("actif") == "1"

    if not banniere_id:
        flash("ID banniere manquant.", "error")
        return redirect(url_for("dashboard.bannieres"))

    if not _verifier_propriete("boutique_bannieres", banniere_id, profile["id"]):
        flash("Action non autorisee.", "error")
        return redirect(url_for("dashboard.bannieres"))

    update_banniere(banniere_id, {"actif": not actif})
    flash(f"Banniere {'desactivee' if actif else 'activee'}.", "success")
    return redirect(url_for("dashboard.bannieres"))


@dashboard_bp.route("/bannieres/options", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def bannieres_options():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    data = {
        "boutique_banniere_arrondie": request.form.get("banniere_arrondie") == "on",
        "boutique_banniere_flou": request.form.get("banniere_flou") == "on",
    }

    try:
        intensite = float(request.form.get("banniere_flou_intensite", 0.45))
        data["boutique_banniere_flou_intensite"] = max(0.1, min(1.0, intensite))
    except Exception:
        pass

    try:
        hauteur = int(request.form.get("banniere_hauteur", 220))
        data["boutique_banniere_hauteur"] = max(150, min(400, hauteur))
    except Exception:
        pass

    ok = update_profile(profile["id"], data)
    if ok:
        flash("Options de banniere mises a jour !", "success")
    else:
        flash("Erreur lors de la sauvegarde.", "error")

    return redirect(url_for("dashboard.bannieres"))


@dashboard_bp.route("/attributs")
@login_required
def attributs():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir
    liste = get_attributs_revendeur(profile["id"])
    return render_template("dashboard/attributs.html", profile=profile, attributs=liste)


@dashboard_bp.route("/attributs/ajouter", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def attributs_ajouter():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    nom = request.form.get("nom", "").strip()[:40]
    type_attr = request.form.get("type", "texte")
    valeurs_str = request.form.get("valeurs", "").strip()[:500]
    obligatoire = request.form.get("obligatoire") == "on"

    if type_attr not in ("texte", "couleur", "taille", "nombre"):
        type_attr = "texte"

    if not nom:
        flash("Le nom de l'attribut est obligatoire.", "error")
        return redirect(url_for("dashboard.attributs"))

    valeurs = []
    if valeurs_str:
        valeurs = [v.strip()[:30] for v in valeurs_str.split(",") if v.strip()][:50]

    result = create_attribut({
        "revendeur_id": profile["id"],
        "nom": nom,
        "type": type_attr,
        "valeurs": valeurs,
        "obligatoire": obligatoire,
        "actif": True,
    })

    if result:
        flash(f"Attribut '{nom}' cree avec succes !", "success")
    else:
        flash("Erreur lors de la creation.", "error")

    return redirect(url_for("dashboard.attributs"))


@dashboard_bp.route("/attributs/modifier", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def attributs_modifier():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    attribut_id = request.form.get("attribut_id", "")
    if not attribut_id:
        flash("ID attribut manquant.", "error")
        return redirect(url_for("dashboard.attributs"))

    if not _verifier_propriete("boutique_attributs", attribut_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative modif attribut {attribut_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard.attributs"))

    nom = request.form.get("nom", "").strip()[:40]
    type_attr = request.form.get("type", "texte")
    valeurs_str = request.form.get("valeurs", "").strip()[:500]
    obligatoire = request.form.get("obligatoire") == "on"

    if type_attr not in ("texte", "couleur", "taille", "nombre"):
        type_attr = "texte"

    valeurs = []
    if valeurs_str:
        valeurs = [v.strip()[:30] for v in valeurs_str.split(",") if v.strip()][:50]

    ok = update_attribut(attribut_id, {
        "nom": nom,
        "type": type_attr,
        "valeurs": valeurs,
        "obligatoire": obligatoire,
    })

    if ok:
        flash("Attribut mis a jour.", "success")
    else:
        flash("Erreur lors de la mise a jour.", "error")

    return redirect(url_for("dashboard.attributs"))


@dashboard_bp.route("/attributs/supprimer", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def attributs_supprimer():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    attribut_id = request.form.get("attribut_id", "")
    if not attribut_id:
        flash("ID attribut manquant.", "error")
        return redirect(url_for("dashboard.attributs"))

    if not _verifier_propriete("boutique_attributs", attribut_id, profile["id"]):
        flash("Action non autorisee.", "error")
        logger.warning(f"Tentative suppression attribut {attribut_id} par revendeur {profile['id']}")
        return redirect(url_for("dashboard.attributs"))

    delete_attribut(attribut_id)
    flash("Attribut supprime.", "success")
    return redirect(url_for("dashboard.attributs"))


@dashboard_bp.route("/attributs/toggle", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def attributs_toggle():
    profile, redir = _get_profile_ou_redirect()
    if redir:
        return redir

    attribut_id = request.form.get("attribut_id", "")
    actif = request.form.get("actif") == "1"

    if not attribut_id:
        flash("ID attribut manquant.", "error")
        return redirect(url_for("dashboard.attributs"))

    if not _verifier_propriete("boutique_attributs", attribut_id, profile["id"]):
        flash("Action non autorisee.", "error")
        return redirect(url_for("dashboard.attributs"))

    update_attribut(attribut_id, {"actif": not actif})
    flash(f"Attribut {'desactive' if actif else 'active'}.", "success")
    return redirect(url_for("dashboard.attributs"))