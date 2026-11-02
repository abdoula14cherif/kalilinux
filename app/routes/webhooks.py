"""
Webhooks globaux : LeekPay, Stripe, Mysoleas, SoleasPay, Abonnements.
SÉCURITÉ MAXIMALE : Signature vérifiée, re-vérification API, idempotence.
"""
import json
import logging
import hashlib
import hmac
from flask import Blueprint, request, jsonify, current_app
from app import limiter
from app.models.database import (
    get_commande_boutique_by_reference,
    update_commande_boutique,
    get_profile,
    get_profile_by_slug,
    update_profile,
    get_plan_by_code,
    appliquer_commission_commande,
    get_demande_retrait,
    update_demande_retrait,
)
from app.models.paiement_config import get_config_decryptee
from app.models.mysoleas import (
    verifier_signature_webhook as verifier_signature_mysoleas,
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
# WEBHOOK SOLEASPAY (Le portefeuille interne)
# ═══════════════════════════════════════════════════════════════

@webhooks_bp.route("/soleaspay", methods=["POST"])
@limiter.limit("600 per hour")
def soleaspay_webhook():
    """
    Webhook global pour SoleasPay (ton compte marchand).
    - Si COLLECTION (paiement client) : crédite le solde_wallet du revendeur.
    - Si DISBURSEMENT (retrait payé) : met à jour le statut du retrait.
    """
    logger.info("[SOLEASPAY WEBHOOK] Received")

    private_key = request.headers.get("x-private-key", "")
    secret = current_app.config.get("MYSOLEAS_WEBHOOK_SECRET", "")
    
    if not secret:
        return jsonify({"error": "config_missing"}), 500

    # Vérification de la signature (SHA256 du secret)
    expected_hash = hashlib.sha256(secret.encode('utf-8')).hexdigest()
    if private_key != expected_hash:
        logger.warning("[SOLEASPAY WEBHOOK] Signature invalide")
        return jsonify({"error": "invalid_signature"}), 401

    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        return jsonify({"error": "invalid_json"}), 400

    operation = data.get("operation", "")
    statut = data.get("status", "")
    invoice_ref = data.get("invoice_reference", "")
    transaction_ref = data.get("transaction_reference", "")

    if not invoice_ref:
        return jsonify({"received": True})

    # ─── CAS 1 : PAIEMENT ENTRANT (COLLECTION) ────────────────
    if operation == "COLLECTION" and statut in ("COMPLETED", "SUCCESS"):
        commande = get_commande_boutique_by_reference(invoice_ref)
        if commande and commande.get("statut_paiement") != "paye":
            
            # Marquer la commande payée
            update_commande_boutique(commande["id"], {
                "statut": "confirmee",
                "statut_paiement": "paye",
                "paiement_reference": transaction_ref,
            })

            # Créditer le Wallet Interne du revendeur
            revendeur = get_profile(commande["revendeur_id"])
            if revendeur:
                solde_actuel = float(revendeur.get("solde_wallet", 0) or 0)
                nouveau_solde = solde_actuel + float(commande.get("total", 0))
                update_profile(revendeur["id"], {"solde_wallet": nouveau_solde})
                
                # Débiter la commission (Credit Boost)
                appliquer_commission_commande(commande, revendeur)

            logger.info(f"[SOLEASPAY] Commande {invoice_ref} payée, wallet crédité.")
        
        return jsonify({"received": True})

    # ─── CAS 2 : RETRAIT PAYÉ (DISBURSEMENT) ──────────────────
    if operation == "DISBURSEMENT":
        demande = get_demande_retrait(invoice_ref)
        if demande:
            if statut in ("COMPLETED", "SUCCESS"):
                update_demande_retrait(demande["id"], {
                    "statut": "paye",
                    "reference_payout": transaction_ref
                })
                logger.info(f"[SOLEASPAY] Retrait {invoice_ref} payé.")
            elif statut in ("FAILED", "CANCELLED"):
                # Rembourser le solde au revendeur
                update_demande_retrait(demande["id"], {"statut": "echec"})
                revendeur = get_profile(demande["revendeur_id"])
                if revendeur:
                    solde_actuel = float(revendeur.get("solde_wallet", 0) or 0)
                    nouveau_solde = solde_actuel + float(demande.get("montant", 0))
                    update_profile(revendeur["id"], {"solde_wallet": nouveau_solde})
                logger.warning(f"[SOLEASPAY] Retrait {invoice_ref} échoué, solde remboursé.")

        return jsonify({"received": True})

    return jsonify({"received": True})


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
# WEBHOOK MYSOLEAS (Ancien système multi-revendeur)
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