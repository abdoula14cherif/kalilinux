"""
Boutique publique d'un revendeur : /r/<slug>
"""
import json
import logging
import secrets
from flask import Blueprint, render_template, redirect, url_for, session, flash, request

from app import limiter
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
    get_produit_by_id,
    create_commande_boutique,
    decrementer_stock,
    get_commande_boutique_by_reference,
    get_boutique_type,
    update_commande_boutique,
    get_moyens_publics_revendeur,
    _url,
    _headers,
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


def _generer_reference():
    return "CMD-" + secrets.token_hex(6).upper()


def _page_boutique_desactivee(boutique_nom):
    """Retourne une page HTML autonome (aucune dependance a un template)."""
    nom_echappe = (boutique_nom or "Cette boutique").replace("<", "&lt;").replace(">", "&gt;")
    return """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Boutique temporairement indisponible</title>
<style>
body{font-family:system-ui,sans-serif;background:linear-gradient(135deg,#0F172A,#1E293B);color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;text-align:center}
.wrap{max-width:500px}
.icon{font-size:4rem;margin-bottom:20px}
h1{font-size:1.6rem;font-weight:900;margin-bottom:14px}
p{font-size:.95rem;opacity:.8;line-height:1.6}
</style>
</head>
<body>
<div class="wrap">
  <div class="icon">🚧</div>
  <h1>__NOM__</h1>
  <p>Cette boutique est temporairement indisponible. Revenez bientot !</p>
</div>
</body>
</html>""".replace("__NOM__", nom_echappe)


# ═══════════════════════════════════════════════════════════════
# VISITE BOUTIQUE
# ═══════════════════════════════════════════════════════════════

@boutique_bp.route("/r/<slug>")
@limiter.limit("120 per minute")
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
        return _page_boutique_desactivee(boutique_nom), 403

    session["revendeur_slug"] = slug

    try:
        incrementer_visite_boutique(revendeur["id"])
    except Exception:
        pass

    type_code = revendeur.get("boutique_type") or "digital"
    type_obj = get_boutique_type(type_code) or {}
    paiement_type_boutique = type_obj.get("paiement_type", "cash")

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

    # Moyens de paiement actifs du revendeur (pour affichage client)
    try:
        moyens_paiement = get_moyens_publics_revendeur(revendeur["id"])
    except Exception as e:
        logger.error(f"visiter moyens_paiement: {type(e).__name__}")
        moyens_paiement = []

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
            moyens_paiement=moyens_paiement,
            paiement_type_boutique=paiement_type_boutique,
            slug=slug,
            est_connecte=est_connecte,
            type_code=type_code,
        )

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
        logger.warning(f"Template {template} introuvable, fallback boutique_produits.html")
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
        moyens_paiement=moyens_paiement,
        paiement_type_boutique=paiement_type_boutique,
        slug=slug,
        est_connecte=est_connecte,
        type_code=type_code,
    )


# ═══════════════════════════════════════════════════════════════
# COMMANDER
# ═══════════════════════════════════════════════════════════════

@boutique_bp.route("/r/<slug>/commander", methods=["POST"])
@limiter.limit("5 per minute; 20 per hour")
def commander(slug):
    revendeur = get_profile_by_slug(slug)
    if not revendeur or not revendeur.get("est_revendeur"):
        flash("Boutique introuvable.", "error")
        return redirect(url_for("home.index"))

    if not revendeur.get("boutique_active", True):
        return _page_boutique_desactivee(revendeur.get("boutique_nom") or slug), 403

    client_nom = request.form.get("client_nom", "").strip()[:100]
    client_telephone = request.form.get("client_telephone", "").strip()[:30]
    client_email = request.form.get("client_email", "").strip()[:150] or None
    client_adresse = request.form.get("client_adresse", "").strip()[:200] or None
    client_ville = request.form.get("client_ville", "").strip()[:80] or None
    note_client = request.form.get("note_client", "").strip()[:500] or None

    if not client_nom or not client_telephone:
        flash("Nom et telephone sont requis.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # ─── DÉTECTION DU TYPE DE BOUTIQUE ──────────────────────
    type_code = revendeur.get("boutique_type") or "general"
    type_obj = get_boutique_type(type_code) or {}
    paiement_type_boutique = type_obj.get("paiement_type", "cash")

    # ─── MÉTHODE DE PAIEMENT CHOISIE ────────────────────────
    mode_paiement = request.form.get("mode_paiement", "cash").strip()[:30]

    # Récupérer les méthodes actives du revendeur
    try:
        moyens_actifs = get_moyens_publics_revendeur(revendeur["id"])
    except Exception:
        moyens_actifs = []

    methodes_autorisees = [m["method"] for m in moyens_actifs]

    # Cash TOUJOURS autorisé
    if mode_paiement == "cash":
        methode_choisie = {"method": "cash", "nom": "Cash à la livraison", "type": "cash"}
    elif mode_paiement in methodes_autorisees:
        methode_choisie = next((m for m in moyens_actifs if m["method"] == mode_paiement), None)
    else:
        flash("Moyen de paiement non disponible pour ce vendeur.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # ─── PANIER ──────────────────────────────────────────────
    panier_json = request.form.get("panier_json", "[]")
    try:
        panier = json.loads(panier_json)
    except Exception:
        panier = []

    if not panier:
        flash("Votre panier est vide.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    sous_total = 0
    produits_commande = []
    for item in panier:
        produit_id = item.get("id")
        try:
            qte = int(item.get("qte", 1))
            qte = max(1, min(100, qte))
        except Exception:
            qte = 1
        produit = get_produit_by_id(produit_id)
        if not produit:
            continue
        if produit.get("revendeur_id") != revendeur["id"]:
            continue
        prix = float(produit.get("prix", 0))
        sous_total += prix * qte
        produits_commande.append({
            "id": produit_id,
            "nom": produit.get("nom"),
            "prix": prix,
            "qte": qte,
            "image": produit.get("image_url"),
            "attributs": item.get("attributs", {}),
            "lien_livraison": produit.get("lien_livraison"),
        })

    if not produits_commande:
        flash("Aucun produit valide dans le panier.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    frais_livraison = 0
    total = sous_total + frais_livraison
    reference = _generer_reference()

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
        "method_paiement": mode_paiement,
        "mode_livraison": "livraison",
        "statut": "en_attente",
        "statut_paiement": "non_paye",
        "note_client": note_client,
    }

    commande = create_commande_boutique(commande_data)

    if not commande:
        flash("Erreur lors de l'enregistrement de la commande.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # ─── NOTIFICATIONS EMAIL ────────────────────────────────
    try:
        from app.models.mailer import (
            email_revendeur_nouvelle_commande,
            email_client_confirmation_commande,
        )

        nom_revendeur = revendeur.get("full_name") or revendeur.get("email", "").split("@")[0]
        nom_boutique = revendeur.get("boutique_nom") or slug.capitalize()
        notif_email = revendeur.get("notif_email") or revendeur.get("email")

        if revendeur.get("notif_nouvelle_commande", True) and notif_email:
            lien_cmd = "https://reseller.boostcentral.world/dashboard/commandes"
            email_revendeur_nouvelle_commande(
                to_email=notif_email,
                nom_revendeur=nom_revendeur,
                nom_boutique=nom_boutique,
                reference=reference,
                client_nom=client_nom,
                client_telephone=client_telephone,
                produits=produits_commande,
                total=total,
                mode_paiement=mode_paiement,
                lien_commandes=lien_cmd
            )

        if client_email:
            lien_client = f"https://reseller.boostcentral.world/r/{slug}/confirmation/{reference}"
            email_client_confirmation_commande(
                to_email=client_email,
                nom_client=client_nom,
                nom_boutique=nom_boutique,
                reference=reference,
                produits=produits_commande,
                total=total,
                lien_confirmation=lien_client,
                whatsapp_vendeur=revendeur.get("boutique_whatsapp") or ""
            )
    except Exception as e:
        logger.error(f"Erreur notification commande: {type(e).__name__}")

    # ─── DÉCRÉMENTER STOCK ───────────────────────────────────
    for p in produits_commande:
        try:
            decrementer_stock(p["id"], p["qte"])
        except Exception:
            pass

    session.pop("panier", None)

    # ═══════════════════════════════════════════════════════════
    # ROUTAGE SELON LE TYPE DE PAIEMENT
    # ═══════════════════════════════════════════════════════════

    if methode_choisie and methode_choisie.get("type") == "en_ligne":
        return redirect(url_for("boutique.paiement_lien",
                                slug=slug,
                                reference=reference))

    elif methode_choisie and methode_choisie.get("type") == "manuel":
        return redirect(url_for("boutique.paiement_manuel",
                                slug=slug,
                                reference=reference))

    # Cash → confirmation normale
    flash(f"Commande {reference} enregistree ! Le vendeur va vous contacter.", "success")
    return redirect(url_for("boutique.confirmation", slug=slug, reference=reference))


# ═══════════════════════════════════════════════════════════════
# PAIEMENT EN LIGNE (Stripe, LeekPay, Mysoleas)
# ═══════════════════════════════════════════════════════════════

@boutique_bp.route("/r/<slug>/paiement-lien/<reference>")
@limiter.limit("120 per minute")
def paiement_lien(slug, reference):
    """
    Crée (ou récupère) le lien LeekPay/Mysoleas pour cette commande.
    Redirige le client vers la page de paiement externe.
    """
    revendeur = get_profile_by_slug(slug)
    if not revendeur or not revendeur.get("est_revendeur"):
        flash("Boutique introuvable.", "error")
        return redirect(url_for("home.index"))

    commande = get_commande_boutique_by_reference(reference)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        flash("Commande introuvable.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    method = commande.get("method_paiement", "cash")

    if method not in ("leekpay", "mysoleas", "stripe"):
        flash("Methode de paiement invalide.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    # ─── LEEKPAY ───────────────────────────────────────────────
    if method == "leekpay":
        from app.models.paiement_config import get_config_decryptee
        from app.models.leekpay import creer_checkout

        config = get_config_decryptee(revendeur["id"], "leekpay")
        if not config or not config.get("config"):
            flash("Paiement LeekPay non configure par le vendeur.", "error")
            return redirect(url_for("boutique.visiter", slug=slug))

        secret_key = config["config"].get("secret_key")
        if not secret_key:
            flash("Configuration LeekPay incomplete.", "error")
            return redirect(url_for("boutique.visiter", slug=slug))

        # Si un checkout existe déjà → rediriger
        if commande.get("paiement_reference") and commande.get("statut_paiement") == "en_cours":
            # TODO : récupérer l'ancien payment_url
            pass

        return_url = url_for("boutique.confirmation",
                              slug=slug, reference=reference, _external=True)
        cancel_url = url_for("boutique.visiter", slug=slug, _external=True)
        webhook_url = url_for("webhooks.leekpay_webhook", slug=slug, _external=True)

        checkout = creer_checkout(
            amount=commande.get("total", 0),
            currency="XOF",
            description=f"Commande {reference}",
            return_url=return_url,
            cancel_url=cancel_url,
            secret_key=secret_key,
            customer_email=commande.get("client_email"),
            customer_name=commande.get("client_nom"),
            customer_phone=commande.get("client_telephone"),
            metadata={
                "commande_reference": reference,
                "revendeur_slug": slug,
            },
            webhook_url=webhook_url,
        )

        if not checkout or not checkout.get("payment_url"):
            flash("Erreur creation du lien de paiement LeekPay. Reessayez.", "error")
            return redirect(url_for("boutique.visiter", slug=slug))

        # Sauvegarder la reference
        update_commande_boutique(commande["id"], {
            "statut_paiement": "en_cours",
            "paiement_reference": checkout.get("id"),
        })

        return redirect(checkout["payment_url"])

    # ─── AUTRES METHODES (a implementer plus tard) ─────────────
    flash("Cette methode de paiement n'est pas encore disponible.", "info")
    return redirect(url_for("boutique.visiter", slug=slug))


# ═══════════════════════════════════════════════════════════════
# PAIEMENT MANUEL (Wave, Orange, MTN, Moov...)
# ═══════════════════════════════════════════════════════════════

@boutique_bp.route("/r/<slug>/paiement-manuel/<reference>")
@limiter.limit("120 per minute")
def paiement_manuel(slug, reference):
    """Affiche les instructions de paiement mobile money manuel."""
    revendeur = get_profile_by_slug(slug)
    if not revendeur or not revendeur.get("est_revendeur"):
        flash("Boutique introuvable.", "error")
        return redirect(url_for("home.index"))

    commande = get_commande_boutique_by_reference(reference)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        flash("Commande introuvable.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    method = commande.get("method_paiement", "cash")

    try:
        moyens = get_moyens_publics_revendeur(revendeur["id"])
        methode_info = next((m for m in moyens if m["method"] == method), None)
    except Exception:
        methode_info = None

    if not methode_info or not methode_info.get("numero"):
        flash("Configuration du vendeur incomplete.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

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

    return render_template(
        "boutique_paiement_manuel.html",
        boutique=boutique,
        commande=commande,
        revendeur=revendeur,
        methode=methode_info,
        slug=slug,
    )


@boutique_bp.route("/r/<slug>/paiement-manuel/<reference>/jai-paye", methods=["POST"])
@limiter.limit("30 per hour")
def paiement_manuel_jai_paye(slug, reference):
    """Le client declare avoir paye → on notifie le revendeur."""
    revendeur = get_profile_by_slug(slug)
    if not revendeur or not revendeur.get("est_revendeur"):
        flash("Boutique introuvable.", "error")
        return redirect(url_for("home.index"))

    commande = get_commande_boutique_by_reference(reference)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        flash("Commande introuvable.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

    update_commande_boutique(commande["id"], {
        "statut_paiement": "client_declare_paye",
    })

    # Notifier le revendeur par email
    try:
        from app.models.mailer import _send, _template
        notif_email = revendeur.get("notif_email") or revendeur.get("email")
        if notif_email:
            contenu = f"""
            <p>Bonjour,</p>
            <p>Le client <b>{commande.get('client_nom')}</b> ({commande.get('client_telephone')})
            declare avoir paye la commande <b>{reference}</b>.</p>
            <p>Montant : <b>{commande.get('total', 0):,.0f} FCFA</b></p>
            <p>Verifiez votre compte puis confirmez la commande.</p>
            """
            _send(
                notif_email,
                f"Client declare avoir paye - {reference}",
                _template("Paiement client a verifier", contenu, "#F59E0B", "#D97706", emoji="💰")
            )
    except Exception as e:
        logger.error(f"Notif paiement manuel: {type(e).__name__}")

    flash("Merci ! Le vendeur va verifier votre paiement et confirmer votre commande.", "success")
    return redirect(url_for("boutique.confirmation", slug=slug, reference=reference))


# ═══════════════════════════════════════════════════════════════
# CONFIRMATION
# ═══════════════════════════════════════════════════════════════

@boutique_bp.route("/r/<slug>/confirmation/<reference>")
@limiter.limit("120 per minute")
def confirmation(slug, reference):
    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        return redirect(url_for("home.index"))

    if not revendeur.get("boutique_active", True):
        return _page_boutique_desactivee(revendeur.get("boutique_nom") or slug), 403

    commande = get_commande_boutique_by_reference(reference)

    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        flash("Commande introuvable.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

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

    return render_template(
        "boutique_confirmation.html",
        boutique=boutique,
        commande=commande,
        revendeur=revendeur,
        slug=slug
    )


# ═══════════════════════════════════════════════════════════════
# MES COMMANDES (côté client)
# ═══════════════════════════════════════════════════════════════

@boutique_bp.route("/r/<slug>/mes-commandes")
@limiter.limit("30 per minute")
def mes_commandes(slug):
    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        flash("Boutique introuvable.", "error")
        return redirect(url_for("home.index"))

    if not revendeur.get("boutique_active", True):
        return _page_boutique_desactivee(revendeur.get("boutique_nom") or slug), 403

    client_id = session.get("boutique_client_id", {}).get(slug, "")

    commandes = []
    if client_id:
        import requests as req_lib
        try:
            r = req_lib.get(
                _url(f"boutique_commandes?revendeur_id=eq.{revendeur['id']}&client_email=eq.{client_id}&order=created_at.desc"),
                headers=_headers(True),
                timeout=10
            )
            commandes = r.json() if r.status_code < 300 else []
        except Exception as e:
            logger.error(f"mes_commandes load: {type(e).__name__}")

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

    return render_template("boutique_mes_commandes.html",
                          boutique=boutique,
                          commandes=commandes,
                          slug=slug,
                          client_id=client_id)


@boutique_bp.route("/r/<slug>/verifier-commandes", methods=["POST"])
@limiter.limit("10 per hour")
def verifier_commandes(slug):
    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        flash("Boutique introuvable.", "error")
        return redirect(url_for("home.index"))

    if not revendeur.get("boutique_active", True):
        return _page_boutique_desactivee(revendeur.get("boutique_nom") or slug), 403

    email = request.form.get("email", "").strip().lower()[:150]
    if not email or "@" not in email:
        flash("Entrez un email valide.", "error")
        return redirect(url_for("boutique.mes_commandes", slug=slug))

    ids = session.get("boutique_client_id", {})
    ids[slug] = email
    session["boutique_client_id"] = ids
    flash(f"Connecte en tant que {email}", "success")

    return redirect(url_for("boutique.mes_commandes", slug=slug))


@boutique_bp.route("/r/<slug>/deconnecter-client")
@limiter.limit("20 per hour")
def deconnecter_client(slug):
    ids = session.get("boutique_client_id", {})
    ids.pop(slug, None)
    session["boutique_client_id"] = ids
    flash("Vous etes deconnecte de cet espace.", "info")
    return redirect(url_for("boutique.visiter", slug=slug))