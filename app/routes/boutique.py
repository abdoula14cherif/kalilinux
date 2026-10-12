"""
Boutique publique d'un revendeur : /r/<slug>
C'est ce que les clients du revendeur voient.
"""
import logging
from flask import Blueprint, render_template, redirect, url_for, session, flash
from app.models.database import (
    get_profile_by_slug,
    get_active_services,
    get_revendeur_prix_all,
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


@boutique_bp.route("/r/<slug>")
def visiter(slug):
    """
    Boutique publique d'un revendeur.
    Si le visiteur n'est pas connecte, on le redirige vers l'inscription
    Boost Central en memorisant le slug pour le rattachement automatique.
    """
    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        flash("Cette boutique n'existe pas ou n'est plus active.", "error")
        return redirect(url_for("home.index"))

    # Memoriser le slug en session pour rattacher le client a l'inscription
    session["revendeur_slug"] = slug

    # Si le revendeur n'a pas encore active son compte → boutique privee
    if not revendeur.get("est_revendeur"):
        flash("Cette boutique n'est pas encore publiee.", "info")
        return redirect(url_for("home.index"))

    # Recuperer les services
    services = get_active_services()
    modele = revendeur.get("revendeur_modele")

    # Filtrer selon le mode
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

    # Grouper par reseau
    services_par_reseau = {}
    for s in services_affiches:
        net = s["reseau"]
        services_par_reseau.setdefault(net, []).append(s)

    # Construire le dict "boutique" avec fallback
    theme = revendeur.get("boutique_theme") or "bleu"
    couleur_principale, couleur_secondaire = THEMES.get(theme, THEMES["bleu"])

    if revendeur.get("boutique_couleur_principale"):
        couleur_principale = revendeur["boutique_couleur_principale"]
    if revendeur.get("boutique_couleur_secondaire"):
        couleur_secondaire = revendeur["boutique_couleur_secondaire"]

    boutique = {
        "nom": revendeur.get("boutique_nom") or f"Boutique {slug.capitalize()}",
        "slogan": revendeur.get("boutique_slogan") or "Boostez vos reseaux sociaux des aujourd'hui",
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
            "Followers, vues, likes, commentaires — livraison rapide, paiement Mobile Money, suivi en temps reel de vos commandes.",
        "a_propos": revendeur.get("boutique_a_propos"),
        "afficher_prix": revendeur.get("boutique_afficher_prix", True),
        "whatsapp_flottant": revendeur.get("boutique_whatsapp_flottant", True),
    }

    # Verifier si le client est connecte
    est_connecte = "user_id" in session

    return render_template(
        "boutique.html",
        revendeur=revendeur,
        boutique=boutique,
        services_par_reseau=services_par_reseau,
        slug=slug,
        est_connecte=est_connecte,
    )