"""
Modele admin — Gestion globale de la plateforme.
SÉCURITÉ : validations strictes, UUID sanitize, plafonds, idempotence.
"""
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import requests
from flask import current_app

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# CONSTANTES DE SÉCURITÉ
# ═══════════════════════════════════════════════════════════════

UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE
)

BALANCE_MIN = 0
BALANCE_MAX = 100_000_000
CREDIT_BOOST_MIN = 0
CREDIT_BOOST_MAX = 10_000_000
MONTANT_ADJUST_MIN = -1_000_000
MONTANT_ADJUST_MAX = 1_000_000

# ═══════════════════════════════════════════════════════════════
# SEUILS CREDIT BOOST (alignés avec database.py)
# ═══════════════════════════════════════════════════════════════

SEUIL_CREDIT_MIN_PUBLICATION = 2000   # Pour publier
SEUIL_CREDIT_ALERTE = 2000            # Alerte visuelle
SEUIL_CREDIT_PAUSE = 500              # Pause automatique

NIVEAUX_ABONNEMENT_VALIDES = ("gratuit", "pro", "business")

TYPES_TRANSACTION_VALIDES = (
    "recharge",
    "debit_commission",
    "remboursement",
    "ajustement_admin_credit",
    "ajustement_admin_debit",
)


def _headers():
    key = current_app.config["SUPABASE_SERVICE_KEY"]
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


def _url(path):
    return current_app.config["SUPABASE_URL"] + "/rest/v1/" + path


# ═══════════════════════════════════════════════════════════════
# VALIDATION SÉCURITÉ
# ═══════════════════════════════════════════════════════════════

def _valider_uuid(value, champ="identifiant"):
    """Verifie qu'une valeur est un UUID valide."""
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not UUID_REGEX.match(value):
        logger.warning(f"[SECURITE] UUID invalide pour {champ}: {value[:50]}")
        return None
    return value


def _valider_montant(valeur, min_val=None, max_val=None, allow_zero=True):
    """Valide un montant numerique. Retourne (montant_float, erreur_str)."""
    if valeur is None or valeur == "":
        return None, "Montant vide"

    try:
        d = Decimal(str(valeur).strip().replace(",", "."))
    except (InvalidOperation, ValueError):
        return None, "Montant invalide"

    if not d.is_finite():
        return None, "Montant invalide (infini ou NaN)"

    if not allow_zero and d == 0:
        return None, "Montant ne peut pas etre zero"

    if min_val is not None and d < Decimal(str(min_val)):
        return None, f"Montant inferieur au minimum ({min_val})"

    if max_val is not None and d > Decimal(str(max_val)):
        return None, f"Montant superieur au maximum ({max_val})"

    return float(d.quantize(Decimal("0.01"))), None


def _valider_raison(raison, min_len=3, max_len=500):
    """Valide une raison/motif obligatoire."""
    if not raison or not isinstance(raison, str):
        return None, "Raison obligatoire"
    raison = raison.strip()
    if len(raison) < min_len:
        return None, f"Raison trop courte (min {min_len} caracteres)"
    if len(raison) > max_len:
        raison = raison[:max_len]
    return raison, None


# ═══════════════════════════════════════════════════════════════
# LOGS ADMIN
# ═══════════════════════════════════════════════════════════════

def log_admin_action(admin_id, action, cible_type=None, cible_id=None,
                     details=None, ip=None):
    """Enregistre une action admin pour audit."""
    try:
        if cible_id and isinstance(cible_id, str):
            cible_id = cible_id[:100]

        payload = {
            "admin_id": admin_id,
            "action": (action or "")[:100],
            "cible_type": (cible_type or "")[:50] or None,
            "cible_id": cible_id,
            "details": details or {},
            "ip": (ip or "")[:45] or None,
        }
        requests.post(_url("admin_logs"), json=payload,
                     headers=_headers(), timeout=10)
    except Exception as e:
        logger.error(f"log_admin_action: {type(e).__name__}")


def get_admin_logs(limit=100):
    """Recupere les derniers logs admin."""
    try:
        limit = max(1, min(int(limit), 500))
        r = requests.get(
            _url(f"admin_logs?order=created_at.desc&limit={limit}"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_admin_logs: {type(e).__name__}")
        return []


# ═══════════════════════════════════════════════════════════════
# STATS GLOBALES
# ═══════════════════════════════════════════════════════════════

def get_stats_globales():
    """Statistiques globales de la plateforme."""
    try:
        r = requests.get(_url("profiles?limit=10000"), headers=_headers(), timeout=15)
        profiles = r.json() if r.status_code < 300 else []
        if not isinstance(profiles, list):
            profiles = []

        revendeurs = [p for p in profiles if p.get("est_revendeur")]
        admins = [p for p in profiles if p.get("est_admin")]
        bannis = [p for p in profiles if p.get("banni")]

        credit_boost_total = sum(
            float(p.get("credit_boost", 0) or 0) for p in profiles
        )
        boutiques_en_pause = sum(
            1 for p in revendeurs if p.get("boutique_active") is False
        )
        credit_negatif = sum(
            1 for p in profiles if float(p.get("credit_boost", 0) or 0) < 0
        )

        r2 = requests.get(_url("boutique_commandes?limit=10000"), headers=_headers(), timeout=15)
        commandes = r2.json() if r2.status_code < 300 else []
        if not isinstance(commandes, list):
            commandes = []

        commandes_livrees = [c for c in commandes if c.get("statut") == "livree"]
        revenus_total = sum(c.get("total", 0) or 0 for c in commandes_livrees)

        commissions_total = 0
        try:
            r3 = requests.get(_url("revendeur_gains?select=commission"),
                            headers=_headers(), timeout=15)
            gains = r3.json() if r3.status_code < 300 else []
            if isinstance(gains, list):
                commissions_total = sum(float(g.get("commission", 0) or 0) for g in gains)
        except Exception:
            pass

        plans_count = {"gratuit": 0, "pro": 0, "business": 0}
        for p in revendeurs:
            niveau = p.get("abonnement_niveau") or "gratuit"
            if niveau in plans_count:
                plans_count[niveau] += 1

        return {
            "nb_utilisateurs": len(profiles),
            "nb_revendeurs": len(revendeurs),
            "nb_admins": len(admins),
            "nb_bannis": len(bannis),
            "nb_commandes": len(commandes),
            "nb_commandes_livrees": len(commandes_livrees),
            "revenus_total": revenus_total,
            "commissions_total": commissions_total,
            "plans_count": plans_count,
            "credit_boost_total": credit_boost_total,
            "boutiques_en_pause": boutiques_en_pause,
            "credit_negatif": credit_negatif,
        }
    except Exception as e:
        logger.error(f"get_stats_globales: {type(e).__name__}")
        return {
            "nb_utilisateurs": 0, "nb_revendeurs": 0, "nb_admins": 0,
            "nb_bannis": 0, "nb_commandes": 0, "nb_commandes_livrees": 0,
            "revenus_total": 0, "commissions_total": 0,
            "plans_count": {"gratuit": 0, "pro": 0, "business": 0},
            "credit_boost_total": 0, "boutiques_en_pause": 0, "credit_negatif": 0,
        }


# ═══════════════════════════════════════════════════════════════
# GESTION DES UTILISATEURS
# ═══════════════════════════════════════════════════════════════

def get_tous_utilisateurs(limit=500, search=None):
    """Liste tous les utilisateurs (avec recherche optionnelle)."""
    try:
        limit = max(1, min(int(limit), 1000))
        url = f"profiles?order=created_at.desc&limit={limit}"
        if search:
            search_clean = re.sub(r"[^\w@.\-\s]", "", search)[:100]
            if search_clean:
                url += f"&or=(email.ilike.*{search_clean}*,full_name.ilike.*{search_clean}*)"
        r = requests.get(_url(url), headers=_headers(), timeout=15)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_tous_utilisateurs: {type(e).__name__}")
        return []


def bannir_utilisateur(user_id, raison=None):
    """Bannit un utilisateur."""
    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        return False

    raison_clean = raison[:500] if raison else None

    try:
        payload = {
            "banni": True,
            "banni_raison": raison_clean,
            "banni_le": datetime.now(timezone.utc).isoformat(),
        }
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"),
                          json=payload, headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"bannir_utilisateur: {type(e).__name__}")
        return False


def debannir_utilisateur(user_id):
    """Debannit un utilisateur."""
    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        return False

    try:
        payload = {"banni": False, "banni_raison": None, "banni_le": None}
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"),
                          json=payload, headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"debannir_utilisateur: {type(e).__name__}")
        return False


def promouvoir_admin(user_id, est_admin=True):
    """Promeut ou retrograde un utilisateur admin."""
    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        return False

    try:
        r = requests.patch(
            _url(f"profiles?id=eq.{user_id}"),
            json={"est_admin": bool(est_admin)},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"promouvoir_admin: {type(e).__name__}")
        return False


def modifier_balance(user_id, nouveau_montant):
    """Modifie le solde d'un utilisateur (admin override)."""
    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        return False, "Identifiant invalide"

    montant, err = _valider_montant(nouveau_montant, BALANCE_MIN, BALANCE_MAX)
    if err:
        return False, err

    try:
        r = requests.patch(
            _url(f"profiles?id=eq.{user_id}"),
            json={"balance": montant},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300, None
    except Exception as e:
        logger.error(f"modifier_balance: {type(e).__name__}")
        return False, "Erreur serveur"


def modifier_abonnement(user_id, niveau):
    """Change l'abonnement d'un revendeur (admin override)."""
    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        return False

    if niveau not in NIVEAUX_ABONNEMENT_VALIDES:
        logger.warning(f"[SECURITE] Niveau abonnement invalide: {niveau}")
        return False

    try:
        commission_pct = 0.10
        try:
            r_plan = requests.get(
                _url(f"abonnements_plans?code=eq.{niveau}&limit=1"),
                headers=_headers(), timeout=10
            )
            plans = r_plan.json()
            if isinstance(plans, list) and plans:
                commission_pct = float(plans[0].get("commission_pct", 0.10))
        except Exception:
            pass

        payload = {
            "abonnement_niveau": niveau,
            "revendeur_commission_pct": commission_pct,
        }
        r = requests.patch(_url(f"profiles?id=eq.{user_id}"),
                          json=payload, headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"modifier_abonnement: {type(e).__name__}")
        return False


def supprimer_utilisateur(user_id):
    """Supprime un utilisateur et toutes ses donnees."""
    user_id = _valider_uuid(user_id, "user_id")
    if not user_id:
        return False

    try:
        r = requests.delete(_url(f"profiles?id=eq.{user_id}"),
                          headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_utilisateur: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# CRÉDIT BOOST — GESTION ADMIN
# ═══════════════════════════════════════════════════════════════

def ajouter_credit_boost(user_id, montant, raison):
    """Ajoute du Credit Boost manuellement (admin)."""
    user_id_clean = _valider_uuid(user_id, "user_id")
    if not user_id_clean:
        return False, "Identifiant utilisateur invalide"

    montant_val, err = _valider_montant(montant, 1, MONTANT_ADJUST_MAX, allow_zero=False)
    if err:
        return False, err

    raison_clean, err = _valider_raison(raison, min_len=5, max_len=500)
    if err:
        return False, err

    try:
        url = _url(f"profiles?id=eq.{user_id_clean}&select=id,email,credit_boost")
        r = requests.get(url, headers=_headers(), timeout=10)
        logger.info(f"[ADMIN CB AJOUT] GET status={r.status_code}")

        if r.status_code >= 300:
            return False, f"Erreur Supabase ({r.status_code})"

        data = r.json()
        if isinstance(data, dict):
            return False, f"Erreur base : {data.get('message', 'inconnue')[:100]}"
        if not isinstance(data, list) or len(data) == 0:
            return False, f"Aucun profil (id={user_id_clean[:8]}...)"

        profil = data[0]
        solde_actuel = float(profil.get("credit_boost", 0) or 0)
        nouveau_solde = solde_actuel + montant_val

        if nouveau_solde > CREDIT_BOOST_MAX:
            return False, f"Solde dépasserait le plafond ({CREDIT_BOOST_MAX:,.0f} F)"

        r2 = requests.patch(
            _url(f"profiles?id=eq.{user_id_clean}"),
            json={"credit_boost": nouveau_solde},
            headers=_headers(), timeout=10
        )

        if r2.status_code >= 300:
            return False, f"Erreur update ({r2.status_code})"

        try:
            _log_credit_boost_transaction(
                user_id_clean, "ajustement_admin_credit", montant_val,
                nouveau_solde, raison_clean, "admin_ajustement", None
            )
        except Exception:
            pass

        # Réactivation auto si on repasse au-dessus du seuil de pause (500)
        if nouveau_solde >= SEUIL_CREDIT_PAUSE:
            _reactiver_boutique_si_besoin(user_id_clean, nouveau_solde)

        logger.info(f"[ADMIN CB AJOUT] +{montant_val} pour {profil.get('email')}")
        return True, None

    except requests.Timeout:
        return False, "Timeout de la base de données"
    except Exception as e:
        logger.exception(f"ajouter_credit_boost: {type(e).__name__}")
        return False, f"Erreur technique ({type(e).__name__})"


def deduire_credit_boost(user_id, montant, raison):
    """Deduit du Credit Boost manuellement (admin)."""
    user_id_clean = _valider_uuid(user_id, "user_id")
    if not user_id_clean:
        return False, "Identifiant utilisateur invalide"

    montant_val, err = _valider_montant(montant, 1, MONTANT_ADJUST_MAX, allow_zero=False)
    if err:
        return False, err

    raison_clean, err = _valider_raison(raison, min_len=5, max_len=500)
    if err:
        return False, err

    try:
        url = _url(f"profiles?id=eq.{user_id_clean}&select=id,email,credit_boost")
        r = requests.get(url, headers=_headers(), timeout=10)
        logger.info(f"[ADMIN CB DEDUIRE] GET status={r.status_code}")

        if r.status_code >= 300:
            return False, f"Erreur Supabase ({r.status_code})"

        data = r.json()
        if isinstance(data, dict):
            return False, f"Erreur base : {data.get('message', 'inconnue')[:100]}"
        if not isinstance(data, list) or len(data) == 0:
            return False, f"Aucun profil (id={user_id_clean[:8]}...)"

        profil = data[0]
        solde_actuel = float(profil.get("credit_boost", 0) or 0)
        nouveau_solde = solde_actuel - montant_val

        r2 = requests.patch(
            _url(f"profiles?id=eq.{user_id_clean}"),
            json={"credit_boost": nouveau_solde},
            headers=_headers(), timeout=10
        )

        if r2.status_code >= 300:
            return False, f"Erreur update ({r2.status_code})"

        try:
            _log_credit_boost_transaction(
                user_id_clean, "ajustement_admin_debit", -montant_val,
                nouveau_solde, raison_clean, "admin_ajustement", None
            )
        except Exception:
            pass

        # ⚠️ NOUVEAU SEUIL : pause si < 500 F (au lieu de 2000)
        if nouveau_solde < SEUIL_CREDIT_PAUSE:
            _mettre_boutique_en_pause(user_id_clean)
            logger.warning(f"[ADMIN CB DEDUIRE] Boutique mise en pause (CB={nouveau_solde})")

        logger.info(f"[ADMIN CB DEDUIRE] -{montant_val} pour {profil.get('email')}")
        return True, None

    except requests.Timeout:
        return False, "Timeout de la base de données"
    except Exception as e:
        logger.exception(f"deduire_credit_boost: {type(e).__name__}")
        return False, f"Erreur technique ({type(e).__name__})"


def get_transactions_credit_boost_admin(user_id=None, limit=200):
    """Historique des transactions Credit Boost (admin)."""
    try:
        limit = max(1, min(int(limit), 1000))
        if user_id:
            user_id = _valider_uuid(user_id, "user_id")
            if not user_id:
                return []
            url = (f"credit_boost_transactions?revendeur_id=eq.{user_id}"
                   f"&order=created_at.desc&limit={limit}")
        else:
            url = f"credit_boost_transactions?order=created_at.desc&limit={limit}"
        r = requests.get(_url(url), headers=_headers(), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_transactions_credit_boost_admin: {type(e).__name__}")
        return []


def get_revendeurs_credit_faible(seuil=2000, limit=100):
    """
    Liste les revendeurs avec credit faible.
    Seuil par defaut = 2000 (alerte). Pour la pause = 500.
    """
    try:
        limit = max(1, min(int(limit), 500))
        r = requests.get(
            _url(f"profiles?est_revendeur=eq.true&credit_boost=lt.{seuil}"
                 f"&order=credit_boost.asc&limit={limit}"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_revendeurs_credit_faible: {type(e).__name__}")
        return []


# ═══════════════════════════════════════════════════════════════
# HELPERS INTERNES
# ═══════════════════════════════════════════════════════════════

def _log_credit_boost_transaction(revendeur_id, type_tx, montant, solde_apres,
                                   description=None, source_type=None,
                                   source_id=None, metadata=None):
    """Enregistre une transaction dans l'historique."""
    try:
        payload = {
            "revendeur_id": revendeur_id,
            "type": type_tx,
            "montant": montant,
            "solde_apres": solde_apres,
            "description": (description or "")[:500] or None,
            "source_type": (source_type or "")[:50] or None,
            "source_id": (source_id or "")[:100] if source_id else None,
            "metadata": metadata or {},
        }
        requests.post(_url("credit_boost_transactions"), json=payload,
                     headers=_headers(), timeout=10)
    except Exception as e:
        logger.error(f"_log_credit_boost_transaction: {type(e).__name__}")


def _reactiver_boutique_si_besoin(user_id, credit_actuel):
    """
    Reactive la boutique si elle etait en pause et que le credit est repasse
    au-dessus du SEUIL_CREDIT_PAUSE (500 F).
    """
    try:
        if credit_actuel < SEUIL_CREDIT_PAUSE:
            return
        r = requests.get(
            _url(f"profiles?id=eq.{user_id}&select=est_revendeur,boutique_active&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        if not data or not isinstance(data, list):
            return
        p = data[0]
        if p.get("est_revendeur") and p.get("boutique_active") is False:
            requests.patch(
                _url(f"profiles?id=eq.{user_id}"),
                json={"boutique_active": True},
                headers=_headers(), timeout=10
            )
            logger.info(f"[ADMIN] Boutique reactivee pour {user_id}")
    except Exception as e:
        logger.error(f"_reactiver_boutique_si_besoin: {type(e).__name__}")


def _mettre_boutique_en_pause(user_id):
    """Met la boutique en pause."""
    try:
        r = requests.get(
            _url(f"profiles?id=eq.{user_id}&select=est_revendeur,boutique_active&limit=1"),
            headers=_headers(), timeout=10
        )
        data = r.json()
        if not data or not isinstance(data, list):
            return
        p = data[0]
        if p.get("est_revendeur") and p.get("boutique_active") is not False:
            requests.patch(
                _url(f"profiles?id=eq.{user_id}"),
                json={"boutique_active": False},
                headers=_headers(), timeout=10
            )
            logger.warning(f"[ADMIN] Boutique mise en pause pour {user_id}")
    except Exception as e:
        logger.error(f"_mettre_boutique_en_pause: {type(e).__name__}")


# ═══════════════════════════════════════════════════════════════
# FONCTIONNALITES DEV
# ═══════════════════════════════════════════════════════════════

def modifier_fonctionnalite(code, data):
    """Modifie une fonctionnalite (nom, icone, couleur, ordre...)."""
    if not code or not isinstance(code, str):
        return False
    code = code.strip()[:50]

    try:
        autorises = {"nom", "description", "icone", "couleur",
                     "est_premium", "actif", "ordre"}
        payload = {k: v for k, v in data.items() if k in autorises}
        if not payload:
            return False
        r = requests.patch(
            _url(f"fonctionnalites_dev?code=eq.{code}"),
            json=payload, headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"modifier_fonctionnalite: {type(e).__name__}")
        return False


def creer_fonctionnalite(data):
    """Cree une nouvelle fonctionnalite."""
    try:
        code = re.sub(r"[^a-z0-9_]", "", (data.get("code") or "").lower())[:50]
        if not code:
            return None
        data["code"] = code

        r = requests.post(_url("fonctionnalites_dev"), json=data,
                         headers=_headers(), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"creer_fonctionnalite: {type(e).__name__}")
        return None


def supprimer_fonctionnalite(code):
    """Supprime une fonctionnalite."""
    if not code or not isinstance(code, str):
        return False
    code = re.sub(r"[^a-z0-9_]", "", code.lower())[:50]
    try:
        r = requests.delete(_url(f"fonctionnalites_dev?code=eq.{code}"),
                          headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_fonctionnalite: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# PLANS — gestion admin
# ═══════════════════════════════════════════════════════════════

def modifier_plan(code, data):
    """Modifie un plan d'abonnement (admin)."""
    if not code:
        return False
    code = re.sub(r"[^a-z0-9_]", "", code.lower())[:30]

    try:
        autorises = {
            "nom", "description", "prix_mensuel", "couleur", "icone",
            "max_produits", "max_categories", "max_bannieres",
            "max_attributs", "max_coupons", "commission_pct",
            "avantages", "actif", "ordre", "populaire"
        }
        payload = {k: v for k, v in data.items() if k in autorises}
        if not payload:
            return False
        r = requests.patch(
            _url(f"abonnements_plans?code=eq.{code}"),
            json=payload, headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"modifier_plan: {type(e).__name__}")
        return False


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS GLOBALES
# ═══════════════════════════════════════════════════════════════

def creer_notification_globale(titre, message, type_notif="info"):
    """Cree une notification globale visible par tous."""
    try:
        titre = (titre or "").strip()[:100]
        message = (message or "").strip()[:500]
        if not titre or not message:
            return None
        if type_notif not in ("info", "success", "warning", "danger"):
            type_notif = "info"

        payload = {
            "titre": titre,
            "message": message,
            "type": type_notif,
            "actif": True,
        }
        r = requests.post(_url("notifications_globales"), json=payload,
                         headers=_headers(), timeout=10)
        result = r.json()
        return result[0] if isinstance(result, list) and result else None
    except Exception as e:
        logger.error(f"creer_notification_globale: {type(e).__name__}")
        return None


def get_notifications_globales(actif_only=True):
    """Liste les notifications globales."""
    try:
        url = "notifications_globales?order=created_at.desc"
        if actif_only:
            url += "&actif=eq.true"
        r = requests.get(_url(url), headers=_headers(), timeout=10)
        data = r.json()
        return data if isinstance(data, list) else []
    except Exception as e:
        logger.error(f"get_notifications_globales: {type(e).__name__}")
        return []


def toggle_notification_globale(notif_id, actif):
    """Active/desactive une notification globale."""
    notif_id = _valider_uuid(notif_id, "notif_id")
    if not notif_id:
        return False
    try:
        r = requests.patch(
            _url(f"notifications_globales?id=eq.{notif_id}"),
            json={"actif": bool(actif)},
            headers=_headers(), timeout=10
        )
        return r.status_code < 300
    except Exception as e:
        logger.error(f"toggle_notification_globale: {type(e).__name__}")
        return False


def supprimer_notification_globale(notif_id):
    """Supprime une notification globale."""
    notif_id = _valider_uuid(notif_id, "notif_id")
    if not notif_id:
        return False
    try:
        r = requests.delete(_url(f"notifications_globales?id=eq.{notif_id}"),
                          headers=_headers(), timeout=10)
        return r.status_code < 300
    except Exception as e:
        logger.error(f"supprimer_notification_globale: {type(e).__name__}")
        return False