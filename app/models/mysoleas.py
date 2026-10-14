"""
Client Python pour l'API Mysoleas (SoleasPay).
Utilise les liens de paiement pour simplifier l'encaissement.
"""
import hashlib
import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)

MYSOLEAS_API_URL = "https://api.mysoleas.com"

PROVIDERS_VALIDES = {
    "mtn_cmr": "MTN Mobile Money Cameroun",
    "orange_cmr": "Orange Money Cameroun",
    "express_union_cmr": "Express Union",
    "mtn_gha": "MTN Ghana",
    "orange_sen": "Orange Senegal",
    "wave_sen": "Wave Senegal",
}

CURRENCIES_VALIDES = {"XAF", "XOF", "USD", "EUR"}

FEE_BEARERS_VALIDES = {"CUSTOMER", "MERCHANT"}


def _headers():
    token = current_app.config.get("MYSOLEAS_APP_TOKEN", "")
    return {
        "x-sp-auth-token": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _url(path):
    base = current_app.config.get("MYSOLEAS_API_URL", MYSOLEAS_API_URL).rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def _valider_montant(amount, currency):
    try:
        amount = float(amount)
    except Exception:
        return None
    if amount <= 0:
        return None
    if currency in ("XAF", "XOF"):
        if amount != int(amount):
            return None
        if amount < 100:
            return None
        return int(amount)
    if currency in ("USD", "EUR"):
        if amount < 0.5:
            return None
        return round(amount, 2)
    return None


def creer_lien_paiement(amount, currency, title, description,
                        provider=None, fee_bearer="CUSTOMER",
                        expires_at=None, max_usage=1,
                        metadata=None):
    """
    Cree un lien de paiement Mysoleas.
    Retourne le dict {reference, short_code, payment_url, status, amount, currency} ou None.
    """
    if currency not in CURRENCIES_VALIDES:
        logger.error(f"Devise invalide : {currency}")
        return None
    if fee_bearer not in FEE_BEARERS_VALIDES:
        fee_bearer = "CUSTOMER"
    if provider and provider not in PROVIDERS_VALIDES:
        logger.error(f"Provider invalide : {provider}")
        return None

    montant_valide = _valider_montant(amount, currency)
    if montant_valide is None:
        logger.error(f"Montant invalide : {amount} {currency}")
        return None

    payload = {
        "amount": montant_valide,
        "currency": currency,
        "feeBearer": fee_bearer,
        "title": (title or "Paiement")[:80],
        "description": (description or "")[:200],
        "max_usage": max(1, min(100, int(max_usage))),
    }

    if provider:
        payload["provider"] = provider
        payload["channel"] = "PROVIDER"
    if expires_at:
        payload["expires_at"] = expires_at
    if metadata and isinstance(metadata, dict):
        payload["metadata"] = metadata

    try:
        r = requests.post(_url("payment-links"), json=payload, headers=_headers(), timeout=30)
        if r.status_code in (200, 201):
            data = r.json()
            if data.get("payment_url"):
                logger.info(f"Lien paiement cree : {data.get('reference')}")
                return data
        logger.error(f"creer_lien_paiement echec: {r.status_code} - {r.text[:200]}")
        return None
    except requests.Timeout:
        logger.error("creer_lien_paiement: timeout")
        return None
    except Exception as e:
        logger.error(f"creer_lien_paiement: {type(e).__name__}")
        return None


def verifier_statut_collection(transaction_reference):
    """
    Verifie le statut d'une collection aupres de Mysoleas.
    Retourne le dict ou None.
    """
    if not transaction_reference:
        return None
    payload = {"transaction_reference": transaction_reference}
    try:
        r = requests.post(_url("collection/status"), json=payload, headers=_headers(), timeout=15)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        logger.error(f"verifier_statut_collection: {type(e).__name__}")
        return None


def verifier_signature_webhook(private_key_recu):
    """
    Verifie que le header x-private-key envoye par Mysoleas
    correspond bien au SHA256 de notre token webhook secret.
    """
    if not private_key_recu:
        return False
    webhook_secret = current_app.config.get("MYSOLEAS_WEBHOOK_SECRET", "")
    if not webhook_secret:
        logger.warning("MYSOLEAS_WEBHOOK_SECRET non configure")
        return False
    attendu = hashlib.sha256(webhook_secret.encode("utf-8")).hexdigest()
    return private_key_recu.strip() == attendu