"""
Webhooks globaux (Mysoleas, etc.)
URL fixe : /webhooks/mysoleas
Le type de paiement (commande boutique, abonnement, recharge) est determine
par le contenu du metadata envoye lors de la creation du lien.
"""
import logging
from flask import Blueprint, request, jsonify
from app import limiter
from app.models.database import (
    get_commande_boutique_by_reference,
    update_commande_boutique,
    get_profile,
    update_profile,
    get_plan_by_code,
    crediter_credit_boost,
    appliquer_commission_commande,
    reactiver_boutique_si_solde_ok,
)
from app.models.mysoleas import (
    verifier_signature_webhook,
    verifier_statut_collection,
)

logger = logging.getLogger(__name__)
webhooks_bp = Blueprint("webhooks", __name__)


STATUTS_SUCCES = ("COMPLETED", "SUCCESSFUL", "SUCCESS", "PAID")
STATUTS_ECHEC = ("FAILED", "CANCELLED", "REJECTED")
STATUTS_EN_COURS = ("PROCESSING", "SUBMITTED", "PENDING")


@webhooks_bp.route("/mysoleas", methods=["POST"])
@limiter.limit("600 per hour")
def mysoleas_webhook():
    """
    Webhook global Mysoleas.
    Gere :
    - paiement commande boutique (type en_ligne) → commission + statut
    - paiement abonnement → activer plan
    - recharge credit_boost → crediter
    """
    # 1. Verifier signature
    private_key = request.headers.get("x-private-key", "")
    if not verifier_signature_webhook(private_key):
        logger.warning("Webhook Mysoleas rejete (signature invalide)")
        return jsonify({"error": "Signature invalide"}), 401

    data = request.get_json(silent=True) or {}
    transaction_ref = data.get("transaction_reference", "")
    invoice_ref = data.get("invoice_reference", "")
    statut = (data.get("status") or "").upper()
    operation = (data.get("operation") or "").upper()
    metadata = data.get("metadata") or {}

    logger.info(f"Webhook Mysoleas : {operation} {statut} pour {invoice_ref}")

    # On ne traite que les COLLECTION
    if operation and operation != "COLLECTION":
        return jsonify({"received": True})

    if not invoice_ref:
        return jsonify({"error": "invoice_reference manquant"}), 400

    # 2. Re-verifier le statut cote API (anti-spoof)
    statut_verifie = statut
    if transaction_ref:
        try:
            verification = verifier_statut_collection(transaction_ref)
            if verification and verification.get("status"):
                statut_verifie = (verification.get("status") or "").upper()
        except Exception as e:
            logger.error(f"verifier_statut_collection: {type(e).__name__}")

    # 3. Determiner le type de paiement
    type_paiement = (metadata.get("type") or "").lower()
    if not type_paiement:
        # Fallback : on essaie de retrouver la commande
        commande = get_commande_boutique_by_reference(invoice_ref)
        if commande:
            type_paiement = "commande_boutique"
        else:
            logger.warning(f"Webhook sans type identifiable : {invoice_ref}")
            return jsonify({"received": True})

    # 4. Router selon le type
    try:
        if type_paiement == "abonnement":
            _traiter_abonnement(invoice_ref, statut_verifie, metadata, transaction_ref)
        elif type_paiement == "recharge_credit_boost":
            _traiter_recharge_credit(invoice_ref, statut_verifie, metadata, transaction_ref)
        elif type_paiement == "commande_boutique":
            _traiter_commande_boutique(invoice_ref, statut_verifie, metadata, transaction_ref)
        else:
            logger.warning(f"Type de paiement inconnu : {type_paiement}")
    except Exception as e:
        logger.error(f"mysoleas_webhook traitement: {type(e).__name__}")
        return jsonify({"received": True, "error": str(e)})

    return jsonify({"received": True})


# ═══════════════════════════════════════════════════════════════
# TRAITEMENTS PAR TYPE
# ═══════════════════════════════════════════════════════════════

def _traiter_abonnement(invoice_ref, statut, metadata, transaction_ref):
    """Active le plan d'abonnement du revendeur."""
    user_id = metadata.get("user_id")
    plan_code = metadata.get("plan_code")
    if not user_id or not plan_code:
        logger.warning(f"Abonnement sans user_id ou plan_code : {invoice_ref}")
        return

    if statut in STATUTS_SUCCES:
        plan = get_plan_by_code(plan_code)
        if not plan:
            return
        commission_pct = float(plan.get("commission_pct", 0.10))
        update_profile(user_id, {
            "abonnement_niveau": plan_code,
            "revendeur_commission_pct": commission_pct,
        })
        logger.info(f"Abonnement {plan_code} active pour {user_id}")
    elif statut in STATUTS_ECHEC:
        logger.info(f"Paiement abonnement echoue : {invoice_ref}")


def _traiter_recharge_credit(invoice_ref, statut, metadata, transaction_ref):
    """Credite le Credit Boost du revendeur."""
    user_id = metadata.get("user_id")
    montant = float(metadata.get("montant", 0) or 0)
    if not user_id or montant <= 0:
        logger.warning(f"Recharge credit sans user_id ou montant : {invoice_ref}")
        return

    if statut in STATUTS_SUCCES:
        crediter_credit_boost(
            user_id, montant,
            description=f"Recharge Credit Boost - {invoice_ref}",
            source_type="recharge_mysoleas",
            source_id=invoice_ref,
            metadata={"transaction_ref": transaction_ref},
        )
        logger.info(f"Credit Boost +{montant} pour {user_id}")


def _traiter_commande_boutique(invoice_ref, statut, metadata, transaction_ref):
    """Confirme le paiement d'une commande boutique en ligne + applique commission."""
    commande = get_commande_boutique_by_reference(invoice_ref)
    if not commande:
        logger.warning(f"Commande introuvable : {invoice_ref}")
        return

    if statut in STATUTS_SUCCES:
        # Mettre a jour le statut
        update_commande_boutique(commande["id"], {
            "statut": "confirmee",
            "statut_paiement": "paye",
            "paiement_reference": transaction_ref or commande.get("paiement_reference"),
        })

        # Recharger la commande mise a jour + appliquer la commission
        commande_maj = get_commande_boutique_by_reference(invoice_ref)
        if commande_maj and not commande_maj.get("commission_appliquee"):
            profil = get_profile(commande_maj.get("revendeur_id"))
            result = appliquer_commission_commande(commande_maj, profil)
            if result and result.get("succes"):
                logger.info(
                    f"Commission appliquee commande {invoice_ref} : "
                    f"{result.get('commission')} (net: {result.get('montant_net')})"
                )
            else:
                logger.warning(f"Echec application commission commande {invoice_ref}")

    elif statut in STATUTS_ECHEC:
        update_commande_boutique(commande["id"], {
            "statut_paiement": "echec",
            "paiement_reference": transaction_ref or commande.get("paiement_reference"),
        })

    elif statut in STATUTS_EN_COURS:
        update_commande_boutique(commande["id"], {
            "statut_paiement": "en_cours",
            "paiement_reference": transaction_ref or commande.get("paiement_reference"),
        })