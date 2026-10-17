"""
Client API Stripe.
Doc : https://docs.stripe.com/api
SÉCURITÉ :
- Ne logge JAMAIS les clés
- Vérifie TOUJOURS la signature des webhooks
- Utilise l'API REST v1
"""
import logging
import json
import requests

logger = logging.getLogger(__name__)

STRIPE_API_URL = "https://api.stripe.com/v1"


def creer_checkout_session(amount, currency, description, success_url, cancel_url,
                            secret_key, customer_email=None, metadata=None,
                            application_fee_amount=None):
    """
    Crée une session Stripe Checkout.
    Retourne {id, url, amount, currency, status} ou None.
    """
    try:
        amount = int(float(amount))
    except Exception:
        logger.error("[STRIPE] Montant invalide")
        return None

    if amount < 50:  # Minimum Stripe = 0.50 EUR/USD, mais pour XAF c'est différent
        logger.error(f"[STRIPE] Montant trop bas : {amount}")
        return None

    # Stripe utilise les centimes (XAF = pas de centimes, donc amount direct)
    # Pour XAF/XOF, Stripe attend le montant en unité de base (ex: 5000 pour 5000 FCFA)
    # Pour EUR/USD, Stripe attend les centimes (ex: 1000 pour 10.00 EUR)
    
    payload = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items[0][price_data][currency]": currency.lower(),
        "line_items[0][price_data][product_data][name]": (description or "Paiement")[:100],
        "line_items[0][price_data][unit_amount]": amount,
        "line_items[0][quantity]": 1,
    }

    if customer_email:
        payload["customer_email"] = customer_email[:150]

    if metadata and isinstance(metadata, dict):
        for k, v in metadata.items():
            payload[f"metadata[{k}]"] = str(v)[:500]

    # application_fee_amount : ta commission (si tu utilises Stripe Connect plus tard)
    # Pour l'instant, on ne l'utilise pas car le revendeur utilise SON compte Stripe.
    # La commission sera débitée de son Credit Boost (comme pour LeekPay/Mysoleas).

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        r = requests.post(
            f"{STRIPE_API_URL}/checkout/sessions",
            data=payload,
            headers=headers,
            timeout=20,
        )
        if r.status_code in (200, 201):
            data = r.json()
            if data.get("url"):
                logger.info(f"[STRIPE] Checkout session cree : {data.get('id')}")
                return {
                    "id": data.get("id"),
                    "url": data.get("url"),
                    "amount": data.get("amount_total"),
                    "currency": data.get("currency"),
                    "status": data.get("payment_status"),
                }
        logger.error(f"[STRIPE] Erreur creation session : {r.status_code} - {r.text[:300]}")
        return None
    except requests.Timeout:
        logger.error("[STRIPE] Timeout creation session")
        return None
    except Exception as e:
        logger.error(f"[STRIPE] Exception creation session : {type(e).__name__}")
        return None


def verifier_checkout_session(session_id, secret_key):
    """
    Vérifie le statut réel d'une session Stripe.
    Retourne le dict complet ou None.
    """
    if not session_id or not secret_key:
        return None

    headers = {
        "Authorization": f"Bearer {secret_key}",
    }

    try:
        r = requests.get(
            f"{STRIPE_API_URL}/checkout/sessions/{session_id}",
            headers=headers,
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        logger.warning(f"[STRIPE] Verification session echouee : {r.status_code}")
        return None
    except Exception as e:
        logger.error(f"[STRIPE] Exception verif session : {type(e).__name__}")
        return None


def verifier_signature_webhook(payload_bytes, signature_header, webhook_secret):
    """
    Vérifie la signature Stripe (header Stripe-Signature).
    Format : t=timestamp,v1=signature
    """
    if not payload_bytes or not signature_header or not webhook_secret:
        return False

    try:
        # Parser le header
        items = dict(item.split("=", 1) for item in signature_header.split(","))
        timestamp = items.get("t", "")
        signature = items.get("v1", "")

        if not timestamp or not signature:
            return False

        # Calculer la signature attendue
        signed_payload = f"{timestamp}.{payload_bytes.decode('utf-8')}"
        import hmac
        import hashlib
        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)
    except Exception as e:
        logger.error(f"[STRIPE] Exception verif signature : {type(e).__name__}")
        return False