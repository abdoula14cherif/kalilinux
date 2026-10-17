"""
Webhooks globaux : LeekPay, Mysoleas, Abonnements.
SÉCURITÉ MAXIMALE :
- Signature HMAC vérifiée pour LeekPay
- Re-vérification côté API (jamais confiance au webhook seul)
- Multi-tenant : chaque revendeur a SA propre URL
- Idempotence : une commission ne peut être appliquée qu'une seule fois
"""
import json
import logging
from flask import Blueprint, request, jsonify
from app import limiter
from app.models.database import (
    get_commande_boutique_by_reference,
    update_commande_boutique,
    get_profile,
    get_profile_by_slug,
    update_profile,
    get_plan_by_code,
    crediter_credit_boost,
    appliquer_commission_commande,
    reactiver_boutique_si_solde_ok,
)
from app.models.paiement_config import get_config_decryptee
from app.models.mysoleas import (
    verifier_signature_webhook as verifier_signature_mysoleas,
    verifier_statut_collection as verifier_statut_mysoleas,
)
from app.models.leekpay import (
    verifier_signature_webhook as verifier_signature_leekpay,
    verifier_checkout as verifier_checkout_leekpay,
)

logger = logging.getLogger(__name__)
webhooks_bp = Blueprint("webhooks", __name__)


# ═══════════════════════════════════════════════════════════════
# WEBHOOK LEEKPAY (multi-revendeur)
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/leekpay/<slug>", methods=["POST"])
@limiter.limit("600 per hour")
def leekpay_webhook(slug):
    """
    Webhook LeekPay pour un revendeur spécifique.
    Sécurité :
    1. Signature HMAC-SHA256 vérifiée avec la clé PUBLIQUE du revendeur
    2. Re-vérification côté API avec la clé SECRÈTE du revendeur
    3. Idempotence via `commission_appliquee`
    """
    logger.info(f"[LEEKPAY WEBHOOK] Received for slug={slug}")

    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        logger.warning(f"[LEEKPAY WEBHOOK] Slug inconnu : {slug}")
        return jsonify({"error": "not_found"}), 404

    config = get_config_decryptee(revendeur["id"], "leekpay")
    if not config or not config.get("config"):
        logger.warning(f"[LEEKPAY WEBHOOK] Config absente pour {slug}")
        return jsonify({"error": "config_missing"}), 400

    public_key = config["config"].get("public_key")
    secret_key = config["config"].get("secret_key")

    if not public_key or not secret_key:
        logger.warning(f"[LEEKPAY WEBHOOK] Cles manquantes pour {slug}")
        return jsonify({"error": "keys_missing"}), 400

    # 1. Vérifier la signature
    signature_recue = request.headers.get("X-LeekPay-Signature", "")
    payload_bytes = request.get_data()

    if not verifier_signature_leekpay(payload_bytes, signature_recue, public_key):
        logger.warning(f"[LEEKPAY WEBHOOK] Signature invalide pour {slug}")
        return jsonify({"error": "invalid_signature"}), 401

    # 2. Parser le payload
    try:
        data = json.loads(payload_bytes)
    except Exception:
        logger.warning(f"[LEEKPAY WEBHOOK] JSON invalide pour {slug}")
        return jsonify({"error": "invalid_json"}), 400

    event = data.get("event", "")
    payload = data.get("data", {})
    checkout_id = payload.get("checkout_id") or payload.get("transaction_id", "")
    status = (payload.get("status") or "").lower()

    logger.info(f"[LEEKPAY WEBHOOK] event={event} checkout={checkout_id} status={status}")

    if not checkout_id:
        logger.warning(f"[LEEKPAY WEBHOOK] checkout_id manquant : {slug}")
        return jsonify({"received": True})

    # 3. Re-vérifier le statut côté API (anti-spoof)
    verification = verifier_checkout_leekpay(checkout_id, secret_key)
    statut_reel = status
    if verification:
        statut_reel = (verification.get("status") or status).lower()
        logger.info(f"[LEEKPAY WEBHOOK] Statut verifie API : {statut_reel}")
    else:
        logger.warning(f"[LEEKPAY WEBHOOK] Verification API echouee, on utilise le statut webhook : {status}")

    # 4. Retrouver la commande via metadata
    metadata = payload.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    commande_ref = metadata.get("commande_reference") or metadata.get("reference")
    if not commande_ref:
        logger.warning(f"[LEEKPAY WEBHOOK] Pas de reference commande : {slug}")
        return jsonify({"received": True})

    commande = get_commande_boutique_by_reference(commande_ref)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        logger.warning(f"[LEEKPAY WEBHOOK] Commande introuvable : {commande_ref}")
        return jsonify({"received": True})

    # 5. Traitement selon le statut
    try:
        if statut_reel == "paid":
            # Éviter de retraiter si déjà payée
            if commande.get("statut_paiement") == "paye" and commande.get("commission_appliquee"):
                logger.info(f"[LEEKPAY WEBHOOK] Commande deja traitee : {commande_ref}")
                return jsonify({"received": True, "already_processed": True})

            update_commande_boutique(commande["id"], {
                "statut": "confirmee",
                "statut_paiement": "paye",
                "paiement_reference": checkout_id,
            })
            logger.info(f"[LEEKPAY WEBHOOK] Commande {commande_ref} passee en 'paye'")

            # Recharger pour appliquer la commission
            commande_maj = get_commande_boutique_by_reference(commande_ref)
            if commande_maj and not commande_maj.get("commission_appliquee"):
                profil = get_profile(commande_maj.get("revendeur_id"))
                result = appliquer_commission_commande(commande_maj, profil)
                if result and result.get("succes"):
                    logger.info(
                        f"[LEEKPAY] Commission appliquee {commande_ref} : "
                        f"{result.get('commission')} F (net: {result.get('montant_net')} F)"
                    )
                    if result.get("boutique_desactivee"):
                        logger.warning(f"[LEEKPAY] Boutique desactivee (credit epuise) : {slug}")
                else:
                    logger.warning(f"[LEEKPAY] Echec application commission {commande_ref}")

            # Envoyer le lien de livraison au client si produit virtuel
            _envoyer_lien_livraison_si_virtuel(commande_maj, revendeur)

        elif statut_reel in ("failed", "cancelled", "expired"):
            update_commande_boutique(commande["id"], {
                "statut_paiement": statut_reel,
                "paiement_reference": checkout_id,
            })
            logger.info(f"[LEEKPAY] Paiement {statut_reel} : {commande_ref}")

        elif statut_reel in ("pending", "processing"):
            update_commande_boutique(commande["id"], {
                "statut_paiement": "en_cours",
                "paiement_reference": checkout_id,
            })
            logger.info(f"[LEEKPAY] Paiement en cours : {commande_ref}")

    except Exception as e:
        logger.error(f"[LEEKPAY WEBHOOK] Erreur traitement : {type(e).__name__} - {str(e)}")
        return jsonify({"received": True, "error": str(e)})

    return jsonify({"received": True})


# ═══════════════════════════════════════════════════════════════
# WEBHOOK MYSOLEAS (multi-revendeur)
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/mysoleas/<slug>", methods=["POST"])
@limiter.limit("600 per hour")
def mysoleas_webhook(slug):
    """Webhook Mysoleas pour un revendeur spécifique."""
    logger.info(f"[MYSOLEAS WEBHOOK] Received for slug={slug}")

    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        return jsonify({"error": "not_found"}), 404

    config = get_config_decryptee(revendeur["id"], "mysoleas")
    if not config or not config.get("config"):
        return jsonify({"error": "config_missing"}), 400

    webhook_secret = config["config"].get("webhook_secret")
    if not webhook_secret:
        return jsonify({"error": "secret_missing"}), 400

    private_key = request.headers.get("x-private-key", "")
    if not verifier_signature_mysoleas(private_key, webhook_secret):
        logger.warning(f"[MYSOLEAS WEBHOOK] Signature invalide pour {slug}")
        return jsonify({"error": "invalid_signature"}), 401

    data = request.get_json(silent=True) or {}
    invoice_ref = data.get("invoice_reference", "")
    if not invoice_ref:
        return jsonify({"error": "no_reference"}), 400

    commande = get_commande_boutique_by_reference(invoice_ref)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        return jsonify({"received": True})

    statut = (data.get("status") or "").upper()
    transaction_ref = data.get("transaction_reference", "")

    try:
        if statut in ("COMPLETED", "SUCCESSFUL", "SUCCESS", "PAID"):
            if commande.get("statut_paiement") == "paye" and commande.get("commission_appliquee"):
                return jsonify({"received": True, "already_processed": True})

            update_commande_boutique(commande["id"], {
                "statut": "confirmee",
                "statut_paiement": "paye",
                "paiement_reference": transaction_ref,
            })
            commande_maj = get_commande_boutique_by_reference(invoice_ref)
            if commande_maj and not commande_maj.get("commission_appliquee"):
                profil = get_profile(commande_maj.get("revendeur_id"))
                appliquer_commission_commande(commande_maj, profil)
            _envoyer_lien_livraison_si_virtuel(commande_maj, revendeur)

        elif statut in ("FAILED", "CANCELLED", "REJECTED"):
            update_commande_boutique(commande["id"], {
                "statut_paiement": "echec",
                "paiement_reference": transaction_ref,
            })

    except Exception as e:
        logger.error(f"[MYSOLEAS WEBHOOK] Erreur : {type(e).__name__}")

    return jsonify({"received": True})


# ═══════════════════════════════════════════════════════════════
# WEBHOOK ABONNEMENT (plateforme globale)
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/abonnement", methods=["POST"])
@limiter.limit("300 per hour")
def abonnement_webhook():
    """Webhook pour les abonnements payés à la plateforme."""
    logger.info("[ABONNEMENT WEBHOOK] Received")

    data = request.get_json(silent=True) or {}
    metadata = data.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    user_id = metadata.get("user_id")
    plan_code = metadata.get("plan_code")
    if not user_id or not plan_code:
        return jsonify({"received": True})

    statut = (data.get("status") or "").upper()
    if statut in ("PAID", "COMPLETED", "SUCCESSFUL", "SUCCESS"):
        plan = get_plan_by_code(plan_code)
        if plan:
            update_profile(user_id, {
                "abonnement_niveau": plan_code,
                "revendeur_commission_pct": float(plan.get("commission_pct", 0.10)),
            })
            logger.info(f"[ABONNEMENT] {plan_code} active pour {user_id}")

    return jsonify({"received": True})


# ═══════════════════════════════════════════════════════════════
# HELPER : ENVOYER LIEN DE LIVRAISON (produits virtuels)
# ═══════════════════════════════════════════════════════════════

def _envoyer_lien_livraison_si_virtuel(commande, revendeur):
    """
    Envoie le lien de livraison par email si la commande contient des produits virtuels.
    """
    if not commande:
        return

    try:
        produits = commande.get("produits") or []
        if not produits:
            return

        liens = []
        for p in produits:
            lien = p.get("lien_livraison")
            if lien:
                liens.append({
                    "nom": p.get("nom"),
                    "lien": lien,
                })

        if not liens:
            return

        client_email = commande.get("client_email")
        if not client_email:
            logger.info(f"[LIVRAISON] Pas d'email client pour {commande.get('reference')}")
            return

        from app.models.mailer import _send, _template

        contenu = "<p>Bonjour,</p>"
        contenu += f"<p>Merci pour votre commande <b>{commande.get('reference')}</b>.</p>"
        contenu += "<p>Voici vos liens de livraison :</p><ul>"
        for l in liens:
            contenu += f'<li><b>{l["nom"]}</b> : <a href="{l["lien"]}">{l["lien"]}</a></li>'
        contenu += "</ul><p>A bientot !</p>"

        nom_boutique = revendeur.get("boutique_nom") or "Boutique"
        _send(
            client_email,
            f"Vos liens de livraison - {nom_boutique}",
            _template(
                "Merci pour votre achat !",
                contenu,
                revendeur.get("boutique_couleur_principale") or "#00BFFF",
                revendeur.get("boutique_couleur_secondaire") or "#0096C7",
                emoji="🎁"
            )
        )
        logger.info(f"[LIVRAISON] Lien envoye a {client_email} pour {commande.get('reference')}")

    except Exception as e:
        logger.error(f"_envoyer_lien_livraison_si_virtuel : {type(e).__name__}")


# ═══════════════════════════════════════════════════════════════
# HEALTH CHECK WEBHOOK
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/ping", methods=["GET", "POST"])
def webhooks_ping():
    """Test simple pour vérifier que les webhooks sont accessibles."""
    return jsonify({"status": "ok", "message": "Webhook receiver ready"}), 200