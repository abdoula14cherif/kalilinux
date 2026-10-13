"""
Boutique publique d'un revendeur : /r/<slug>
"""
import logging
from flask import Blueprint, render_template, redirect, url_for, session, flash
from app.models.database import (
    get_profile_by_slug,
    get_active_services,
    get_revendeur_prix_all,
    incrementer_visite_boutique,
    get_produits_revendeur,
    get_categories_par_type,
    get_bannieres_revendeur,
    get_avis_revendeur,
    get_attributs_revendeur,
)

logger = logging.getLogger(__name__)
boutique_bp = Blueprint("boutique", __name__)

THEMES = {
    "bleu":   ("#0066FF", "#0047CC"),
    "violet": ("#7C3AED", "#4C1D95"),
    "vert":   ("#059669", "#047857"),
    "orange": ("#F97316", "#EA580C"),
    "noir":   ("#0F172A", "#1E293B"),
    "rouge":  ("#DC2626", "#991B1B"),
}


def _template_pour_type(type_code):
    templates = {
        "digital":      "boutique.html",
        "formations":   "boutique_formations.html",
        "restauration": "boutique_restauration.html",
        "mode":         "boutique_produits.html",
        "beaute":       "boutique_produits.html",
        "ebooks":       "boutique_produits.html",
        "electronique": "boutique_produits.html",
        "immobilier":   "boutique_produits.html",
        "art":          "boutique_produits.html",
        "general":      "boutique_produits.html",
    }
    return templates.get(type_code, "boutique_produits.html")


@boutique_bp.route("/r/<slug>")
def visiter(slug):
    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        flash("Cette boutique n'existe pas.", "error")
        return redirect(url_for("home.index"))

    if not revendeur.get("est_revendeur"):
        flash("Cette boutique n'est pas encore publiee.", "info")
        return redirect(url_for("home.index"))

    if not revendeur.get("boutique_active", True):
        boutique_nom = revendeur.get("boutique_nom") or slug.capitalize()
        return render_template("boutique_desactivee.html", boutique_nom=boutique_nom), 403

    session["revendeur_slug"] = slug

    try:
        incrementer_visite_boutique(revendeur["id"])
    except Exception:
        pass

    type_code = revendeur.get("boutique_type") or "digital"

    theme = revendeur.get("boutique_theme") or "bleu"
    couleur_principale, couleur_secondaire = THEMES.get(theme, THEMES["bleu"])
    if revendeur.get("boutique_couleur_principale"):
        couleur_principale = revendeur["boutique_couleur_principale"]
    if revendeur.get("boutique_couleur_secondaire"):
        couleur_secondaire = revendeur["boutique_couleur_secondaire"]

    boutique = {
        "nom": revendeur.get("boutique_nom") or f"Boutique {slug.capitalize()}",
        "slogan": revendeur.get("boutique_slogan") or "Decouvrez notre boutique",
        "logo_url": revendeur.get("boutique_logo_url"),
        "banniere_url": revendeur.get("boutique_banniere_url"),
        "theme": theme,
        "couleur_principale": couleur_principale,
        "couleur_secondaire": couleur_secondaire,
        "whatsapp": revendeur.get("boutique_whatsapp"),
        "email": revendeur.get("boutique_email"),
        "facebook": revendeur.get("boutique_facebook"),
        "instagram": revendeur.get("boutique_instagram"),
        "tiktok": revendeur.get("boutique_tiktok"),
        "telegram": revendeur.get("boutique_telegram"),
        "message_accueil": revendeur.get("boutique_message_accueil") or
            "Decouvrez notre selection de produits et services.",
        "a_propos": revendeur.get("boutique_a_propos"),
        "afficher_prix": revendeur.get("boutique_afficher_prix", True),
        "whatsapp_flottant": revendeur.get("boutique_whatsapp_flottant", True),
        "type_grille": revendeur.get("boutique_type_grille") or "grille",
        "services_par_ligne": revendeur.get("boutique_services_par_ligne") or 3,
        "sections": revendeur.get("boutique_sections_affichees") or {
            "stats": True, "avantages": True, "comment": True,
            "services": True, "apropos": True, "avis": True, "faq": True
        },
        "badge_verifie": revendeur.get("boutique_badge_verifie", False),
        "note": revendeur.get("boutique_note") or 4.9,
        "nb_avis": revendeur.get("boutique_nb_avis") or 0,
        "slogan_anime": revendeur.get("boutique_slogan_anime", False),
    }

    stats_boutique = {
        "visites": revendeur.get("boutique_visites", 0) or 0,
        "clients": revendeur.get("referral_count", 0) or 0,
        "note": boutique["note"],
        "nb_avis": boutique["nb_avis"],
    }

    est_connecte = "user_id" in session

    # ═══════════════════════════════════════════════════════════════
    # BANNIÈRES + AVIS + ATTRIBUTS (nouveaux)
    # ═══════════════════════════════════════════════════════════════
    try:
        bannieres = get_bannieres_revendeur(revendeur["id"], only_active=True)
    except Exception:
        bannieres = []

    try:
        avis_approuves = get_avis_revendeur(revendeur["id"], only_approuve=True)
    except Exception:
        avis_approuves = []

    try:
        attributs = get_attributs_revendeur(revendeur["id"], only_active=True)
    except Exception:
        attributs = []

    # =============== DIGITAL ===============
    if type_code == "digital":
        services = get_active_services()
        modele = revendeur.get("revendeur_modele")

        services_affiches = []
        if modele == "marge":
            mes_prix = {p["service_id"]: p["prix_fcfa"] for p in get_revendeur_prix_all(revendeur["id"])}
            for s in services:
                if s["id"] in mes_prix:
                    s2 = dict(s)
                    s2["prix_affiche"] = mes_prix[s["id"]]
                    services_affiches.append(s2)
        else:
            for s in services:
                s2 = dict(s)
                s2["prix_affiche"] = s["prix_fcfa"]
                services_affiches.append(s2)

        services_par_reseau = {}
        for s in services_affiches:
            net = s["reseau"]
            services_par_reseau.setdefault(net, []).append(s)

        return render_template(
            "boutique.html",
            revendeur=revendeur,
            boutique=boutique,
            services_par_reseau=services_par_reseau,
            stats_boutique=stats_boutique,
            bannieres=bannieres,
            avis_approuves=avis_approuves,
            attributs=attributs,
            slug=slug,
            est_connecte=est_connecte,
            type_code=type_code,
        )

    # =============== AUTRES ===============
    produits = get_produits_revendeur(revendeur["id"], only_active=True)
    categories = get_categories_par_type(type_code)

    produits_par_categorie = {}
    for p in produits:
        cat_id = p.get("categorie_id") or 0
        produits_par_categorie.setdefault(cat_id, []).append(p)

    template = _template_pour_type(type_code)

    from flask import current_app
    try:
        current_app.jinja_env.get_template(template)
    except Exception:
        logger.warning(f"Template {template} introuvable, fallback sur boutique_produits.html")
        template = "boutique_produits.html"
        try:
            current_app.jinja_env.get_template(template)
        except Exception:
            logger.error("Aucun template disponible !")
            flash("Cette boutique est en cours de configuration.", "info")
            return redirect(url_for("home.index"))

    return render_template(
        template,
        revendeur=revendeur,
        boutique=boutique,
        produits=produits,
        categories=categories,
        produits_par_categorie=produits_par_categorie,
        stats_boutique=stats_boutique,
        bannieres=bannieres,
        avis_approuves=avis_approuves,
        attributs=attributs,
        slug=slug,
        est_connecte=est_connecte,
        type_code=type_code,
    )

import re
import secrets
from datetime import datetime, timezone


def _generer_reference():
    """Genere une reference unique pour la commande."""
    return "CMD-" + secrets.token_hex(6).upper()


@boutique_bp.route("/r/<slug>/commander", methods=["POST"])
def commander(slug):
    """Traite la commande invite (sans compte)."""
    revendeur = get_profile_by_slug(slug)
    if not revendeur or not revendeur.get("est_revendeur"):
        flash("Boutique introuvable.", "error")
        return redirect(url_for("home.index"))

    from flask import request

    # Recuperer les infos client
    client_nom = request.form.get("client_nom", "").strip()
    client_telephone = request.form.get("client_telephone", "").strip()
    client_email = request.form.get("client_email", "").strip() or None
    client_adresse = request.form.get("client_adresse", "").strip() or None
    client_ville = request.form.get("client_ville", "").strip() or None
    mode_paiement = request.form.get("mode_paiement", "cash")
    note_client = request.form.get("note_client", "").strip() or None

    if not client_nom or not client_telephone:
        flash("Nom et telephone sont requis.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # Recuperer les produits du panier (JSON envoye par le client)
    panier_json = request.form.get("panier_json", "[]")
    try:
        import json
        panier = json.loads(panier_json)
    except Exception:
        panier = []

    if not panier:
        flash("Votre panier est vide.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # Calculer le total
    sous_total = 0
    produits_commande = []
    for item in panier:
        produit_id = item.get("id")
        qte = int(item.get("qte", 1))
        produit = get_produit_by_id(produit_id)
        if not produit:
            continue
        prix = float(produit.get("prix", 0))
        sous_total += prix * qte
        produits_commande.append({
            "id": produit_id,
            "nom": produit.get("nom"),
            "prix": prix,
            "qte": qte,
            "image": produit.get("image_url"),
            "attributs": item.get("attributs", {})
        })

    if not produits_commande:
        flash("Aucun produit valide dans le panier.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # Frais de livraison (0 par defaut, modifiable plus tard)
    frais_livraison = 0
    total = sous_total + frais_livraison

    # Generer une reference unique
    reference = _generer_reference()

    # Creer la commande
    from app.models.database import create_commande_boutique, decrementer_stock

    commande_data = {
        "revendeur_id": revendeur["id"],
        "reference": reference,
        "client_nom": client_nom,
        "client_email": client_email,
        "client_telephone": client_telephone,
        "client_adresse": client_adresse,
        "client_ville": client_ville,
        "produits": produits_commande,
        "sous_total": sous_total,
        "frais_livraison": frais_livraison,
        "total": total,
        "mode_paiement": mode_paiement,
        "mode_livraison": "livraison",
        "statut": "en_attente",
        "note_client": note_client,
    }

    commande = create_commande_boutique(commande_data)

    if not commande:
        flash("Erreur lors de l'enregistrement de la commande.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # Decrementer le stock
    for p in produits_commande:
        try:
            decrementer_stock(p["id"], p["qte"])
        except Exception:
            pass

    # Vider le panier cote client
    session.pop("panier", None)

    flash(f"✅ Commande {reference} enregistree ! Le vendeur va vous contacter.", "success")
    return redirect(url_for("boutique.confirmation", slug=slug, reference=reference))


@boutique_bp.route("/r/<slug>/confirmation/<reference>")
def confirmation(slug, reference):
    """Page de confirmation apres commande."""
    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        return redirect(url_for("home.index"))

    from app.models.database import get_commande_boutique_by_reference
    commande = get_commande_boutique_by_reference(reference)

    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        flash("Commande introuvable.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # Theme
    theme = revendeur.get("boutique_theme") or "bleu"
    couleur_principale, couleur_secondaire = THEMES.get(theme, THEMES["bleu"])
    if revendeur.get("boutique_couleur_principale"):
        couleur_principale = revendeur["boutique_couleur_principale"]
    if revendeur.get("boutique_couleur_secondaire"):
        couleur_secondaire = revendeur["boutique_couleur_secondaire"]

    boutique = {
        "nom": revendeur.get("boutique_nom") or f"Boutique {slug.capitalize()}",
        "logo_url": revendeur.get("boutique_logo_url"),
        "couleur_principale": couleur_principale,
        "couleur_secondaire": couleur_secondaire,
        "whatsapp": revendeur.get("boutique_whatsapp"),
    }

    return render_template("boutique_confirmation.html",
                          boutique=boutique,
                          commande=commande,
                          revendeur=revendeur,
                          slug=slug)