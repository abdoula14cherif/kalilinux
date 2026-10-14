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
<meta name="theme-color" content="#0F172A">
<title>Boutique temporairement indisponible</title>
<style>
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
body{
  font-family:'Segoe UI',system-ui,-apple-system,sans-serif;
  min-height:100vh;
  background:linear-gradient(135deg,#0F172A,#1E293B);
  color:#fff;
  display:flex;
  align-items:center;
  justify-content:center;
  padding:20px;
  line-height:1.5;
  -webkit-font-smoothing:antialiased;
  position:relative;
  overflow:hidden;
}
body::before{
  content:'';
  position:absolute;
  top:-50%;
  right:-20%;
  width:80%;
  height:200%;
  background:radial-gradient(circle,rgba(0,191,255,.15) 0%,transparent 65%);
  pointer-events:none;
}
.wrap{
  max-width:520px;
  width:100%;
  text-align:center;
  position:relative;
  z-index:1;
  padding:40px 24px;
}
.icon-wrap{
  width:110px;
  height:110px;
  border-radius:50%;
  background:rgba(0,191,255,.15);
  border:2px solid rgba(0,191,255,.4);
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:3rem;
  color:#00BFFF;
  margin:0 auto 28px;
  animation:pulse 2s ease-in-out infinite;
}
@keyframes pulse{
  0%,100%{box-shadow:0 0 0 0 rgba(0,191,255,.4)}
  50%{box-shadow:0 0 0 20px rgba(0,191,255,0)}
}
h1{
  font-size:1.7rem;
  font-weight:900;
  margin-bottom:14px;
  line-height:1.2;
  background:linear-gradient(90deg,#00BFFF,#7DD3FC);
  -webkit-background-clip:text;
  background-clip:text;
  color:transparent;
}
.shop-name{
  display:inline-block;
  background:rgba(0,191,255,.1);
  border:1px solid rgba(0,191,255,.3);
  color:#7DD3FC;
  padding:6px 16px;
  border-radius:20px;
  font-size:.82rem;
  font-weight:800;
  margin-bottom:20px;
  letter-spacing:.3px;
}
p{
  font-size:.95rem;
  color:rgba(255,255,255,.7);
  line-height:1.7;
  margin-bottom:14px;
  max-width:440px;
  margin-left:auto;
  margin-right:auto;
}
p strong{color:#fff;font-weight:800}
.info-box{
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.1);
  border-radius:16px;
  padding:20px 22px;
  margin:26px 0;
  text-align:left;
}
.info-box h3{
  font-size:.82rem;
  font-weight:900;
  color:#00BFFF;
  text-transform:uppercase;
  letter-spacing:.8px;
  margin-bottom:12px;
}
.info-box ul{list-style:none;padding:0}
.info-box li{
  font-size:.85rem;
  color:rgba(255,255,255,.75);
  padding:8px 0;
  padding-left:22px;
  position:relative;
  line-height:1.5;
}
.info-box li::before{
  content:'\\25B8';
  position:absolute;
  left:0;
  color:#10B981;
  font-weight:900;
}
.actions{
  display:flex;
  gap:12px;
  justify-content:center;
  flex-wrap:wrap;
  margin-top:8px;
}
.btn{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:9px;
  padding:14px 26px;
  border-radius:12px;
  font-weight:800;
  font-size:.92rem;
  text-decoration:none;
  transition:all .25s;
  border:none;
  cursor:pointer;
  font-family:inherit;
  min-width:170px;
}
.btn-primary{
  background:linear-gradient(135deg,#00BFFF,#0096C7);
  color:#fff;
  box-shadow:0 8px 22px rgba(0,191,255,.35);
}
.btn-primary:hover{transform:translateY(-2px)}
.btn-outline{
  background:rgba(255,255,255,.08);
  color:#fff;
  border:1.5px solid rgba(255,255,255,.2);
}
.btn-outline:hover{background:rgba(255,255,255,.15)}
.footer{
  margin-top:36px;
  font-size:.78rem;
  color:rgba(255,255,255,.35);
}
.footer a{color:#00BFFF;text-decoration:none;font-weight:700}
@media(max-width:520px){
  h1{font-size:1.4rem}
  .icon-wrap{width:90px;height:90px;font-size:2.4rem}
  .actions{flex-direction:column}
  .btn{width:100%}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="icon-wrap">🚧</div>
  <div class="shop-name">🏪 BOUTIQUE_NAME_PLACEHOLDER</div>
  <h1>Boutique temporairement indisponible</h1>
  <p>Cette boutique est actuellement <strong>fermée</strong> par son propriétaire. Elle sera de nouveau accessible très bientôt.</p>
  <div class="info-box">
    <h3>Que faire ?</h3>
    <ul>
      <li>Revenez dans quelques heures, la boutique pourrait réouvrir</li>
      <li>Contactez directement le vendeur si vous avez son numéro</li>
      <li>Découvrez d'autres boutiques sur Boost Central</li>
    </ul>
  </div>
  <div class="actions">
    <a href="https://boostcentral.world" class="btn btn-primary">🌐 Voir Boost Central</a>
    <a href="javascript:history.back()" class="btn btn-outline">← Retour</a>
  </div>
  <div class="footer">
    Propulsé par <a href="https://boostcentral.world" target="_blank">Boost Central</a> © 2026
  </div>
</div>
</body>
</html>""".replace("BOUTIQUE_NAME_PLACEHOLDER", nom_echappe)


@boutique_bp.route("/r/<slug>")
@limiter.limit("60 per minute")
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
        slug=slug,
        est_connecte=est_connecte,
        type_code=type_code,
    )


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
    mode_paiement = request.form.get("mode_paiement", "cash")
    note_client = request.form.get("note_client", "").strip()[:500] or None

    if mode_paiement not in ("cash", "mtn", "orange"):
        mode_paiement = "cash"

    if not client_nom or not client_telephone:
        flash("Nom et telephone sont requis.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

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
            "attributs": item.get("attributs", {})
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
        "mode_livraison": "livraison",
        "statut": "en_attente",
        "note_client": note_client,
    }

    commande = create_commande_boutique(commande_data)

    if not commande:
        flash("Erreur lors de l'enregistrement de la commande.", "error")
        return redirect(url_for("boutique.visiter", slug=slug))

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

    for p in produits_commande:
        try:
            decrementer_stock(p["id"], p["qte"])
        except Exception:
            pass

    session.pop("panier", None)

    flash(f"Commande {reference} enregistree ! Le vendeur va vous contacter.", "success")
    return redirect(url_for("boutique.confirmation", slug=slug, reference=reference))


@boutique_bp.route("/r/<slug>/confirmation/<reference>")
@limiter.limit("30 per minute")
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
        from app.models.database import _url, _headers
        import requests
        try:
            r = requests.get(
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



@boutique_bp.route("/r/<slug>/paiement/creer-lien", methods=["POST"])
@limiter.limit("10 per hour")
def paiement_creer_lien(slug):
    """Cree un lien de paiement Mysoleas pour une commande."""
    from flask import jsonify
    from app.models.mysoleas import creer_lien_paiement
    from app.models.database import update_commande_boutique

    revendeur = get_profile_by_slug(slug)
    if not revendeur or not revendeur.get("est_revendeur"):
        return jsonify({"error": "Boutique introuvable"}), 404

    if not revendeur.get("boutique_active", True):
        return jsonify({"error": "Boutique desactivee"}), 403

    commande_ref = request.form.get("commande_reference", "").strip()
    provider = request.form.get("provider", "").strip() or None

    if not commande_ref:
        return jsonify({"error": "Reference commande manquante"}), 400

    commande = get_commande_boutique_by_reference(commande_ref)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        return jsonify({"error": "Commande introuvable"}), 404

    if commande.get("statut") == "payee":
        return jsonify({"error": "Cette commande est deja payee"}), 400

    lien = creer_lien_paiement(
        amount=commande.get("total", 0),
        currency="XAF",
        title=f"Commande {commande_ref}",
        description=f"Paiement de votre commande sur {revendeur.get('boutique_nom') or slug}",
        provider=provider,
        fee_bearer="CUSTOMER",
        max_usage=1,
        metadata={
            "commande_reference": commande_ref,
            "revendeur_slug": slug,
        },
    )

    if not lien or not lien.get("payment_url"):
        return jsonify({"error": "Erreur creation du lien. Reessayez."}), 500

    try:
        update_commande_boutique(commande["id"], {
            "statut_paiement": "en_attente",
            "paiement_reference": lien.get("reference"),
        })
    except Exception as e:
        logger.error(f"update_commande paiement_reference: {type(e).__name__}")

    return jsonify({
        "success": True,
        "payment_url": lien.get("payment_url"),
        "reference": lien.get("reference"),
        "short_code": lien.get("short_code"),
    })


@boutique_bp.route("/r/<slug>/paiement/webhook", methods=["POST"])
@limiter.limit("300 per hour")
def paiement_webhook(slug):
    """
    Webhook appele par Mysoleas a chaque changement de statut.
    Met a jour le statut de la commande.
    """
    from flask import jsonify
    from app.models.mysoleas import verifier_signature_webhook, verifier_statut_collection
    from app.models.database import update_commande_boutique

    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        return jsonify({"error": "Boutique introuvable"}), 404

    private_key = request.headers.get("x-private-key", "")
    if not verifier_signature_webhook(private_key):
        logger.warning(f"Webhook Mysoleas rejete (signature invalide) - slug={slug}")
        return jsonify({"error": "Signature invalide"}), 401

    data = request.get_json(silent=True) or {}
    transaction_ref = data.get("transaction_reference", "")
    invoice_ref = data.get("invoice_reference", "")
    statut = (data.get("status") or "").upper()
    operation = (data.get("operation") or "").upper()

    logger.info(f"Webhook Mysoleas : {operation} {statut} pour {invoice_ref}")

    if operation != "COLLECTION":
        return jsonify({"received": True})

    if not invoice_ref:
        return jsonify({"error": "invoice_reference manquant"}), 400

    commande = get_commande_boutique_by_reference(invoice_ref)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        return jsonify({"error": "Commande introuvable"}), 404

    statut_verifie = statut
    if transaction_ref:
        try:
            verification = verifier_statut_collection(transaction_ref)
            if verification and verification.get("status"):
                statut_verifie = (verification.get("status") or "").upper()
        except Exception as e:
            logger.error(f"verifier_statut webhook: {type(e).__name__}")

    try:
        if statut_verifie in ("COMPLETED", "SUCCESSFUL", "SUCCESS", "PAID"):
            update_commande_boutique(commande["id"], {
                "statut": "confirmee",
                "statut_paiement": "paye",
                "paiement_reference": transaction_ref or commande.get("paiement_reference"),
            })
            logger.info(f"Paiement confirme pour {invoice_ref}")
        elif statut_verifie in ("FAILED", "CANCELLED", "REJECTED"):
            update_commande_boutique(commande["id"], {
                "statut_paiement": "echec",
                "paiement_reference": transaction_ref or commande.get("paiement_reference"),
            })
            logger.info(f"Paiement echoue pour {invoice_ref}")
        elif statut_verifie in ("PROCESSING", "SUBMITTED", "PENDING"):
            update_commande_boutique(commande["id"], {
                "statut_paiement": "en_cours",
                "paiement_reference": transaction_ref or commande.get("paiement_reference"),
            })
    except Exception as e:
        logger.error(f"update_commande webhook: {type(e).__name__}")

    return jsonify({"received": True})