"""
Chiffrement / Déchiffrement des clés API sensibles.
SÉCURITÉ MAXIMALE :
- AES-128 via Fernet (standard industriel)
- Clé de chiffrement stockée UNIQUEMENT dans Vercel (jamais en DB)
- Aucune clé en clair n'est jamais loggée
- Toute erreur de déchiffrement retourne None (fail-safe)
"""
import os
import logging
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class CryptoError(Exception):
    """Erreur de chiffrement/déchiffrement."""
    pass


def _get_fernet():
    """
    Récupère l'instance Fernet depuis ENCRYPTION_KEY.
    Lève une exception si la clé est absente ou invalide.
    """
    key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not key:
        logger.critical("[CRYPTO] ENCRYPTION_KEY manquante dans les variables d'environnement")
        raise CryptoError("Clé de chiffrement non configurée")
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.critical(f"[CRYPTO] ENCRYPTION_KEY invalide : {type(e).__name__}")
        raise CryptoError("Clé de chiffrement invalide")


def encrypt(texte_clair):
    """
    Chiffre un texte en clair.
    Retourne le texte chiffré en base64, ou None en cas d'erreur.
    """
    if not texte_clair:
        return None
    try:
        f = _get_fernet()
        return f.encrypt(texte_clair.encode("utf-8")).decode("utf-8")
    except CryptoError:
        return None
    except Exception as e:
        logger.error(f"[CRYPTO] encrypt error : {type(e).__name__}")
        return None


def decrypt(texte_chiffre):
    """
    Déchiffre un texte chiffré.
    Retourne le texte clair, ou None en cas d'erreur.
    """
    if not texte_chiffre:
        return None
    try:
        f = _get_fernet()
        return f.decrypt(texte_chiffre.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.warning("[CRYPTO] Token invalide (corrompu ou mauvaise clé)")
        return None
    except CryptoError:
        return None
    except Exception as e:
        logger.error(f"[CRYPTO] decrypt error : {type(e).__name__}")
        return None


def masquer(texte_clair, prefixe_visible=6):
    """
    Masque une clé pour l'affichage.
    Ex : sk_live_abcd1234xyz → sk_liv••••••••••
    """
    if not texte_clair or not isinstance(texte_clair, str):
        return "—"
    if len(texte_clair) <= prefixe_visible:
        return "•" * len(texte_clair)
    return texte_clair[:prefixe_visible] + "•" * (len(texte_clair) - prefixe_visible)


def chiffrer_dict(data):
    """
    Chiffre un dictionnaire entier (pour stocker une config complexe).
    Retourne le JSON chiffré.
    """
    if not data or not isinstance(data, dict):
        return None
    try:
        import json
        payload = json.dumps(data, separators=(",", ":"))
        return encrypt(payload)
    except Exception as e:
        logger.error(f"[CRYPTO] chiffrer_dict error : {type(e).__name__}")
        return None


def dechiffrer_dict(texte_chiffre):
    """
    Déchiffre un JSON chiffré et retourne le dict.
    Retourne {} en cas d'erreur.
    """
    if not texte_chiffre:
        return {}
    try:
        import json
        clair = decrypt(texte_chiffre)
        if not clair:
            return {}
        return json.loads(clair)
    except Exception as e:
        logger.error(f"[CRYPTO] dechiffrer_dict error : {type(e).__name__}")
        return {}


def tester_configuration():
    """
    Auto-test : chiffre puis déchiffre une valeur.
    Retourne True si le système fonctionne.
    """
    try:
        test = "test-123-xyz"
        chiffre = encrypt(test)
        if not chiffre:
            return False
        dechiffre = decrypt(chiffre)
        return dechiffre == test
    except Exception as e:
        logger.error(f"[CRYPTO] tester_configuration error : {type(e).__name__}")
        return False