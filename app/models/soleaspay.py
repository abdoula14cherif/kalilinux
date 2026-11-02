import logging
import requests
import uuid
from flask import current_app

logger = logging.getLogger(__name__)

MYSOLEAS_API_URL = "https://api.mysoleas.com"

def _headers():
    token = current_app.config.get("MYSOLEAS_APP_TOKEN", "")
    return {
        "x-sp-auth-token": f"Bearer {token}",
        "Content-Type": "application/json",
    }

# ─── PAIEMENT (COLLECTION / PAY-IN) ─────────────────────────
def creer_intention_paiement(amount, currency, provider, customer_wallet, description, invoice_ref):
    payload = {
        "amount": amount,
        "currency": currency,
        "transaction_uuid": str(uuid.uuid4()),
        "provider": provider,
        "channel": "PROVIDER",
        "customer_wallet": customer_wallet,
        "description": description
    }
    try:
        r = requests.post(f"{MYSOLEAS_API_URL}/collection/intent", json=payload, headers=_headers(), timeout=15)
        if r.status_code in (200, 201):
            return r.json() # Contient transaction_reference
        logger.error(f"[SOLEASPAY] Erreur intent: {r.text}")
        return None
    except Exception as e:
        logger.error(f"[SOLEASPAY] Exception intent: {type(e).__name__}")
        return None

def executer_paiement(transaction_reference, invoice_reference):
    payload = {
        "transaction_reference": transaction_reference,
        "invoice_reference": invoice_reference
    }
    try:
        r = requests.post(f"{MYSOLEAS_API_URL}/collection/execute", json=payload, headers=_headers(), timeout=15)
        if r.status_code in (200, 201):
            return r.json()
        return None
    except Exception as e:
        logger.error(f"[SOLEASPAY] Exception execute: {type(e).__name__}")
        return None

# ─── RETRAIT (DISBURSEMENT / PAY-OUT) ───────────────────────
def creer_intention_payout(amount, provider, customer_wallet, description, payout_ref):
    payload = {
        "amount": amount,
        "currency": "XAF",
        "transaction_uuid": str(uuid.uuid4()),
        "provider": provider,
        "channel": "PROVIDER",
        "customer_wallet": customer_wallet,
        "description": description
    }
    try:
        r = requests.post(f"{MYSOLEAS_API_URL}/disbursement/intent", json=payload, headers=_headers(), timeout=15)
        if r.status_code in (200, 201):
            return r.json() # Contient transaction_reference et fee
        logger.error(f"[SOLEASPAY] Erreur payout intent: {r.text}")
        return None
    except Exception as e:
        logger.error(f"[SOLEASPAY] Exception payout intent: {type(e).__name__}")
        return None

def executer_payout(transaction_reference, payout_ref):
    payload = {
        "transaction_reference": transaction_reference,
        "invoice_reference": payout_ref
    }
    try:
        r = requests.post(f"{MYSOLEAS_API_URL}/disbursement/execute", json=payload, headers=_headers(), timeout=15)
        if r.status_code in (200, 201):
            return r.json()
        return None
    except Exception as e:
        logger.error(f"[SOLEASPAY] Exception payout execute: {type(e).__name__}")
        return None

# ─── VERIFICATION STATUT ────────────────────────────────────
def verifier_statut(transaction_reference, type_op="collection"):
    payload = {"transaction_reference": transaction_reference}
    endpoint = "collection/status" if type_op == "collection" else "disbursement/status"
    try:
        r = requests.post(f"{MYSOLEAS_API_URL}/{endpoint}", json=payload, headers=_headers(), timeout=15)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None