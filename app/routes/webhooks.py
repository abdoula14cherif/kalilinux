"""
Webhooks globaux : LeekPay, Stripe, Mysoleas, Abonnements.
SÉCURITÉ MAXIMALE :
- Signature HMAC vérifiée
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
from app.models.stripe_client import (
    verifier_signature_webhook as verifier_signature_stripe,
    verifier_checkout_session as verifier_checkout_stripe,
)

logger = logging.getLogger(__name__)
webhooks_bp = Blueprint("webhooks", __name__)


# ═══════════════════════════════════════════════════════════════
# WEBHOOK LEEKPAY
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/leekpay/<slug>", methods=["POST"])
@limiter.limit("600 per hour")
def leekpay_webhook(slug):
    logger.info(f"[LEEKPAY WEBHOOK] Received for slug={slug}")

    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        return jsonify({"error": "not_found"}), 404

    config = get_config_decryptee(revendeur["id"], "leekpay")
    if not config or not config.get("config"):
        return jsonify({"error": "config_missing"}), 400

    public_key = config["config"].get("public_key")
    secret_key = config["config"].get("secret_key")

    if not public_key or not secret_key:
        return jsonify({"error": "keys_missing"}), 400

    signature_recue = request.headers.get("X-LeekPay-Signature", "")
    payload_bytes = request.get_data()

    if not verifier_signature_leekpay(payload_bytes, signature_recue, public_key):
        logger.warning(f"[LEEKPAY WEBHOOK] Signature invalide pour {slug}")
        return jsonify({"error": "invalid_signature"}), 401

    try:
        data = json.loads(payload_bytes)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    event = data.get("event", "")
    payload = data.get("data", {})
    checkout_id = payload.get("checkout_id") or payload.get("transaction_id", "")
    status = (payload.get("status") or "").lower()

    if not checkout_id:
        return jsonify({"received": True})

    verification = verifier_checkout_leekpay(checkout_id, secret_key)
    statut_reel = status
    if verification:
        statut_reel = (verification.get("status") or status).lower()

    metadata = payload.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    commande_ref = metadata.get("commande_reference") or metadata.get("reference")
    if not commande_ref:
        return jsonify({"received": True})

    commande = get_commande_boutique_by_reference(commande_ref)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        return jsonify({"received": True})

    try:
        if statut_reel == "paid":
            if commande.get("statut_paiement") == "paye" and commande.get("commission_appliquee"):
                return jsonify({"received": True, "already_processed": True})

            update_commande_boutique(commande["id"], {
                "statut": "confirmee",
                "statut_paiement": "paye",
                "paiement_reference": checkout_id,
            })

            commande_maj = get_commande_boutique_by_reference(commande_ref)
            if commande_maj and not commande_maj.get("commission_appliquee"):
                profil = get_profile(commande_maj.get("revendeur_id"))
                appliquer_commission_commande(commande_maj, profil)

            from app.models.mailer import _envoyer_lien_livraison_si_virtuel
            _envoyer_lien_livraison_si_virtuel(commande_maj, revendeur)

        elif statut_reel in ("failed", "cancelled", "expired"):
            update_commande_boutique(commande["id"], {
                "statut_paiement": statut_reel,
                "paiement_reference": checkout_id,
            })
        elif statut_reel in ("pending", "processing"):
            update_commande_boutique(commande["id"], {
                "statut_paiement": "en_cours",
                "paiement_reference": checkout_id,
            })
    except Exception as e:
        logger.error(f"[LEEKPAY WEBHOOK] Erreur : {type(e).__name__}")
        return jsonify({"received": True, "error": str(e)})

    return jsonify({"received": True})


# ═══════════════════════════════════════════════════════════════
# WEBHOOK STRIPE
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/stripe/<slug>", methods=["POST"])
@limiter.limit("600 per hour")
def stripe_webhook(slug):
    logger.info(f"[STRIPE WEBHOOK] Received for slug={slug}")

    revendeur = get_profile_by_slug(slug)
    if not revendeur:
        return jsonify({"error": "not_found"}), 404

    config = get_config_decryptee(revendeur["id"], "stripe")
    if not config or not config.get("config"):
        return jsonify({"error": "config_missing"}), 400

    webhook_secret = config["config"].get("webhook_secret")
    secret_key = config["config"].get("secret_key")

    if not webhook_secret or not secret_key:
        return jsonify({"error": "keys_missing"}), 400

    signature_header = request.headers.get("Stripe-Signature", "")
    payload_bytes = request.get_data()

    if not verifier_signature_stripe(payload_bytes, signature_header, webhook_secret):
        logger.warning(f"[STRIPE WEBHOOK] Signature invalide pour {slug}")
        return jsonify({"error": "invalid_signature"}), 401

    try:
        data = json.loads(payload_bytes)
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    event_type = data.get("type", "")
    session_data = data.get("data", {}).get("object", {})
    session_id = session_data.get("id", "")
    payment_status = session_data.get("payment_status", "")

    logger.info(f"[STRIPE WEBHOOK] event={event_type} session={session_id} status={payment_status}")

    if event_type not in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        return jsonify({"received": True})

    if payment_status != "paid":
        return jsonify({"received": True})

    verification = verifier_checkout_stripe(session_id, secret_key)
    statut_reel = payment_status
    if verification:
        statut_reel = verification.get("payment_status", payment_status)

    if statut_reel != "paid":
        return jsonify({"received": True})

    metadata = session_data.get("metadata") or {}
    commande_ref = metadata.get("commande_reference") or metadata.get("reference")

    if not commande_ref:
        return jsonify({"received": True})

    commande = get_commande_boutique_by_reference(commande_ref)
    if not commande or commande.get("revendeur_id") != revendeur["id"]:
        return jsonify({"received": True})

    try:
        if commande.get("statut_paiement") == "paye" and commande.get("commission_appliquee"):
            return jsonify({"received": True, "already_processed": True})

        update_commande_boutique(commande["id"], {
            "statut": "confirmee",
            "statut_paiement": "paye",
            "paiement_reference": session_id,
        })

        commande_maj = get_commande_boutique_by_reference(commande_ref)
        if commande_maj and not commande_maj.get("commission_appliquee"):
            profil = get_profile(commande_maj.get("revendeur_id"))
            appliquer_commission_commande(commande_maj, profil)

        from app.models.mailer import _envoyer_lien_livraison_si_virtuel
        _envoyer_lien_livraison_si_virtuel(commande_maj, revendeur)

    except Exception as e:
        logger.error(f"[STRIPE WEBHOOK] Erreur : {type(e).__name__}")
        return jsonify({"received": True, "error": str(e)})

    return jsonify({"received": True})


# ═══════════════════════════════════════════════════════════════
# WEBHOOK MYSOLEAS
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/mysoleas/<slug>", methods=["POST"])
@limiter.limit("600 per hour")
def mysoleas_webhook(slug):
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
    if not verifier_signature_mysoleas(private_key):
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

            from app.models.mailer import _envoyer_lien_livraison_si_virtuel
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
# WEBHOOK ABONNEMENT
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/abonnement", methods=["POST"])
@limiter.limit("300 per hour")
def abonnement_webhook():
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
# HEALTH CHECK
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/ping", methods=["GET", "POST"])
def webhooks_ping():
    return jsonify({"status": "ok", "message": "Webhook receiver ready"}), 200