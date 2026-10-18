"""
Client API Mysoleas / SoleasPay
Doc : https://api.mysoleas.com
"""
import logging
import requests
from flask import current_app

logger = logging.getLogger(__name__)

MYSOLEAS_API_URL = "https://api.mysoleas.com"

def _headers():
    token = current_app.config.get("MYSOLEAS_APP_TOKEN", "")
    return {
        "x-sp-auth-token": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def creer_intention_paiement(amount, currency, transaction_uuid, provider, customer_wallet, description):
    """Crée une intention de paiement (Pay-In)."""
    payload = {
        "amount": amount,
        "currency": currency,
        "transaction_uuid": transaction_uuid,
        "provider": provider, # ex: 'mtn_cmr', 'orange_cmr'
        "channel": "PROVIDER",
        "customer_wallet": customer_wallet,
        "description": description
    }
    try:
        r = requests.post(f"{MYSOLEAS_API_URL}/collection/intent", json=payload, headers=_headers(), timeout=15)
        if r.status_code in (200, 201):
            return r.json()
        logger.error(f"[SOLEASPAY] Erreur intent: {r.status_code} - {r.text}")
        return None
    except Exception as e:
        logger.error(f"[SOLEASPAY] Exception intent: {type(e).__name__}")
        return None

def executer_paiement(transaction_reference, invoice_reference):
    """Exécute le paiement après création de l'intention."""
    payload = {
        "transaction_reference": transaction_reference,
        "invoice_reference": invoice_reference
    }
    try:
        r = requests.post(f"{MYSOLEAS_API_URL}/collection/execute", json=payload, headers=_headers(), timeout=15)
        if r.status_code in (200, 201):
            return r.json()
        logger.error(f"[SOLEASPAY] Erreur execute: {r.status_code} - {r.text}")
        return None
    except Exception as e:
        logger.error(f"[SOLEASPAY] Exception execute: {type(e).__name__}")
        return None

def verifier_statut_paiement(transaction_reference):
    """Vérifie le statut réel d'une transaction."""
    payload = {"transaction_reference": transaction_reference}
    try:
        r = requests.post(f"{MYSOLEAS_API_URL}/collection/status", json=payload, headers=_headers(), timeout=15)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception as e:
        logger.error(f"[SOLEASPAY] Exception status: {type(e).__name__}")
        return None