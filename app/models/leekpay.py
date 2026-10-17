"""
Client API LeekPay.
API doc : https://leekpay.me/docs
SÉCURITÉ :
- Ne logge JAMAIS les clés API
- Vérifie TOUJOURS le statut côté serveur (jamais confiance au navigateur)
- Signature webhook = HMAC-SHA256 avec la clé PUBLIQUE
"""
import hmac
import hashlib
import logging
import requests

logger = logging.getLogger(__name__)

LEEKPAY_API_URL = "https://leekpay.fr/api/v1"


# ═══════════════════════════════════════════════════════════════
# CRÉER UN CHECKOUT
# ═══════════════════════════════════════════════════════════════

def creer_checkout(amount, currency, description, return_url,
                    secret_key, customer_email=None, customer_name=None,
                    customer_phone=None, metadata=None,
                    webhook_url=None, cancel_url=None):
    """
    Crée un checkout LeekPay.
    Retourne le dict {id, payment_url, amount, currency, status, ...} ou None.
    """
    try:
        amount = int(float(amount))
    except Exception:
        logger.error("[LEEKPAY] montant invalide")
        return None

    if amount < 100:
        logger.error(f"[LEEKPAY] montant trop bas : {amount}")
        return None

    if currency not in ("XOF", "EUR", "USD", "XAF"):
        logger.error(f"[LEEKPAY] devise invalide : {currency}")
        return None

    payload = {
        "amount": amount,
        "currency": "XOF" if currency == "XAF" else currency,
        "description": (description or "")[:500],
        "return_url": return_url,
    }

    if cancel_url:
        payload["cancel_url"] = cancel_url
    if webhook_url:
        payload["webhook_url"] = webhook_url
    if customer_email:
        payload["customer_email"] = customer_email[:150]
    if customer_name:
        payload["customer_name"] = customer_name[:150]
    if customer_phone:
        payload["customer_phone"] = customer_phone[:30]
    if metadata and isinstance(metadata, dict):
        payload["metadata"] = metadata

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        r = requests.post(
            f"{LEEKPAY_API_URL}/checkout",
            json=payload,
            headers=headers,
            timeout=20,
        )
        if r.status_code in (200, 201):
            data = r.json()
            if data.get("success") and data.get("data", {}).get("payment_url"):
                logger.info(f"[LEEKPAY] Checkout cree : {data['data'].get('id')}")
                return data["data"]
        logger.error(f"[LEEKPAY] Erreur creation checkout : {r.status_code} - {r.text[:200]}")
        return None
    except requests.Timeout:
        logger.error("[LEEKPAY] Timeout creation checkout")
        return None
    except Exception as e:
        logger.error(f"[LEEKPAY] Exception creation checkout : {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# VÉRIFIER LE STATUT D'UN CHECKOUT
# ═══════════════════════════════════════════════════════════════

def verifier_checkout(checkout_id, secret_key):
    """
    Vérifie le statut réel d'un checkout LeekPay.
    Retourne le dict complet ou None.
    """
    if not checkout_id or not secret_key:
        return None

    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
    }

    try:
        r = requests.get(
            f"{LEEKPAY_API_URL}/checkout/{checkout_id}",
            headers=headers,
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("data"):
                return data["data"]
        logger.warning(f"[LEEKPAY] Verification checkout echouee : {r.status_code}")
        return None
    except Exception as e:
        logger.error(f"[LEEKPAY] Exception verif checkout : {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# VÉRIFIER SIGNATURE WEBHOOK
# ═══════════════════════════════════════════════════════════════

def verifier_signature_webhook(payload_bytes, signature_recue, public_key):
    """
    Vérifie la signature HMAC-SHA256 envoyée par LeekPay.
    IMPORTANT : LeekPay utilise la clé PUBLIQUE (pas la secrète) pour signer.
    """
    if not payload_bytes or not signature_recue or not public_key:
        return False

    try:
        expected = hmac.new(
            public_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_recue.strip().lower())
    except Exception as e:
        logger.error(f"[LEEKPAY] Exception verif signature : {type(e).__name__}")
        return False