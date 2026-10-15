"""
Boost Reseller - SDK Python Officiel
=====================================
Client Python moderne pour l'API Boost Reseller.

Installation :
    pip install requests

Utilisation rapide :
    from boost_reseller import BoostReseller

    client = BoostReseller(api_key="bsk_live_xxxx")

    # Verifier la connexion
    if client.ping():
        print("Connexion OK")

    # Boutique
    boutique = client.boutique.get()
    print(boutique["nom"])

    # Produits
    for p in client.produits.iterate():
        print(p["nom"], p["prix"])

    # Commandes
    commandes = client.commandes.list(statut="en_attente")

    # Stats
    stats = client.stats.get(periode="30j")

Fonctionnalites :
    - Retry automatique sur erreurs reseau et 5xx
    - Gestion du rate limit (429)
    - Pagination automatique avec iterate()
    - Logging optionnel
    - Support de toutes les ressources API v1

Version : 2.0.0
Licence : MIT
"""

import logging
import time

import requests

__version__ = "2.0.0"
__all__ = [
    "BoostReseller",
    "BoostResellerError",
    "Produit",
    "Commande",
    "Client",
    "Banniere",
    "Categorie",
    "Attribut",
    "Coupon",
    "Avis",
]


logger = logging.getLogger("boost_reseller")


# ═══════════════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════════════

class BoostResellerError(Exception):
    """Erreur renvoyee par l'API Boost Reseller."""
    def __init__(self, message, code=None, status=None, response=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.response = response

    def __repr__(self):
        return f"BoostResellerError(code={self.code!r}, status={self.status!r}, message={str(self)!r})"


class RateLimitError(BoostResellerError):
    """Erreur de rate limit (HTTP 429)."""
    def __init__(self, message, retry_after=None):
        super().__init__(message, code="rate_limit", status=429)
        self.retry_after = retry_after


# ═══════════════════════════════════════════════════════════════
# OBJETS RICHES (bonus : acces par attribut en plus du dict)
# ═══════════════════════════════════════════════════════════════

class _RichObject(dict):
    """Dict enrichi permettant acces par attribut ET par cle."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"Attribut '{name}' introuvable")

    def __setattr__(self, name, value):
        self[name] = value

    def __repr__(self):
        if "id" in self:
            return f"<{type(self).__name__} id={self['id']}>"
        if "reference" in self:
            return f"<{type(self).__name__} ref={self['reference']}>"
        if "nom" in self:
            return f"<{type(self).__name__} nom={self['nom']!r}>"
        return f"<{type(self).__name__} keys={list(self.keys())}>"


class Produit(_RichObject): pass
class Commande(_RichObject): pass
class Client(_RichObject): pass
class Banniere(_RichObject): pass
class Categorie(_RichObject): pass
class Attribut(_RichObject): pass
class Coupon(_RichObject): pass
class Avis(_RichObject): pass


# ═══════════════════════════════════════════════════════════════
# CLASSE DE BASE POUR LES RESSOURCES
# ═══════════════════════════════════════════════════════════════

class _BaseResource:
    def __init__(self, client):
        self._client = client

    def _get(self, endpoint, params=None):
        return self._client._request("GET", endpoint, params=params)

    def _post(self, endpoint, data=None):
        return self._client._request("POST", endpoint, json=data)

    def _patch(self, endpoint, data=None):
        return self._client._request("PATCH", endpoint, json=data)

    def _delete(self, endpoint):
        return self._client._request("DELETE", endpoint)


# ═══════════════════════════════════════════════════════════════
# RESSOURCE : BOUTIQUE
# ═══════════════════════════════════════════════════════════════

class BoutiqueResource(_BaseResource):
    """Ressource pour la boutique."""

    def get(self):
        """Recupere les informations de la boutique."""
        return self._get("/boutique")

    def update(self, **champs):
        """Met a jour les champs de la boutique."""
        return self._patch("/boutique", champs)


# ═══════════════════════════════════════════════════════════════
# RESSOURCE : PRODUITS
# ═══════════════════════════════════════════════════════════════

class ProduitsResource(_BaseResource):
    """Ressource pour les produits."""

    def list(self, limit=50, offset=0, actif=None, categorie_id=None):
        """Liste les produits avec pagination et filtres."""
        params = {"limit": limit, "offset": offset}
        if actif is not None:
            params["actif"] = "true" if actif else "false"
        if categorie_id is not None:
            params["categorie_id"] = categorie_id
        data = self._get("/produits", params=params)
        return [Produit(p) for p in data.get("produits", [])]

    def iterate(self, page_size=50, actif=None, categorie_id=None):
        """Itere sur TOUS les produits automatiquement (pagination)."""
        offset = 0
        while True:
            batch = self.list(limit=page_size, offset=offset, actif=actif, categorie_id=categorie_id)
            if not batch:
                break
            for item in batch:
                yield item
            if len(batch) < page_size:
                break
            offset += page_size

    def get(self, produit_id):
        """Recupere un produit par son ID."""
        return Produit(self._get(f"/produits/{produit_id}"))

    def create(self, nom, prix, description=None, stock=None, categorie_id=None):
        """Cree un nouveau produit."""
        payload = {"nom": nom, "prix": prix}
        if description is not None:
            payload["description"] = description
        if stock is not None:
            payload["stock"] = stock
        if categorie_id is not None:
            payload["categorie_id"] = categorie_id
        return Produit(self._post("/produits", payload))

    def update(self, produit_id, **champs):
        """Met a jour un produit existant."""
        return self._patch(f"/produits/{produit_id}", champs)

    def delete(self, produit_id):
        """Supprime un produit."""
        return self._delete(f"/produits/{produit_id}")


# ═══════════════════════════════════════════════════════════════
# RESSOURCE : COMMANDES
# ═══════════════════════════════════════════════════════════════

class CommandesResource(_BaseResource):
    """Ressource pour les commandes."""

    def list(self, limit=50, offset=0, statut=None):
        """Liste les commandes."""
        params = {"limit": limit, "offset": offset}
        if statut:
            params["statut"] = statut
        data = self._get("/commandes", params=params)
        return [Commande(c) for c in data.get("commandes", [])]

    def iterate(self, page_size=50, statut=None):
        """Itere sur TOUTES les commandes automatiquement."""
        offset = 0
        while True:
            batch = self.list(limit=page_size, offset=offset, statut=statut)
            if not batch:
                break
            for item in batch:
                yield item
            if len(batch) < page_size:
                break
            offset += page_size

    def get(self, reference):
        """Recupere une commande par sa reference."""
        return Commande(self._get(f"/commandes/{reference}"))

    def update(self, reference, statut):
        """Met a jour le statut d'une commande."""
        return self._patch(f"/commandes/{reference}", {"statut": statut})

    def confirmer(self, reference):
        """Raccourci : confirme une commande."""
        return self.update(reference, "confirmee")

    def livrer(self, reference):
        """Raccourci : marque une commande comme livree."""
        return self.update(reference, "livree")

    def annuler(self, reference):
        """Raccourci : annule une commande."""
        return self.update(reference, "annulee")


# ═══════════════════════════════════════════════════════════════
# RESSOURCE : CLIENTS
# ═══════════════════════════════════════════════════════════════

class ClientsResource(_BaseResource):
    """Ressource pour les clients."""

    def list(self, limit=50):
        """Liste les clients inscrits sur votre boutique."""
        data = self._get("/clients", params={"limit": limit})
        return [Client(c) for c in data.get("clients", [])]


# ═══════════════════════════════════════════════════════════════
# RESSOURCE : STATS
# ═══════════════════════════════════════════════════════════════

class StatsResource(_BaseResource):
    """Ressource pour les statistiques."""

    def get(self, periode="all"):
        """Recupere les statistiques (periode : 7j, 30j, 90j, 1an, all)."""
        return self._get("/stats", params={"periode": periode})


# ═══════════════════════════════════════════════════════════════
# CLIENT PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class BoostReseller:
    """
    Client principal pour l'API Boost Reseller.

    Args:
        api_key (str): Votre cle API (format bsk_live_xxxx)
        base_url (str): URL de base de l'API (defaut : production)
        timeout (int): Timeout des requetes en secondes (defaut : 30)
        max_retries (int): Nombre de tentatives sur erreurs 5xx/429 (defaut : 3)
        debug (bool): Active les logs de debug
    """

    DEFAULT_BASE_URL = "https://reseller.boostcentral.world/api/v1"

    def __init__(self, api_key, base_url=None, timeout=30, max_retries=3, debug=False):
        if not api_key or not isinstance(api_key, str) or not api_key.startswith("bsk_live_"):
            raise BoostResellerError(
                "Cle API invalide. Format attendu : bsk_live_xxxx",
                code="invalid_api_key"
            )
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))

        if debug:
            logging.basicConfig(level=logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.WARNING)

        # Ressources
        self.boutique = BoutiqueResource(self)
        self.produits = ProduitsResource(self)
        self.commandes = CommandesResource(self)
        self.clients = ClientsResource(self)
        self.stats = StatsResource(self)

    # ─── Requete HTTP centrale ────────────────────────────────

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"BoostReseller-Python/{__version__}",
        }
        kwargs.setdefault("timeout", self.timeout)
        kwargs["headers"] = headers

        last_exception = None
        for tentative in range(self.max_retries + 1):
            try:
                logger.debug(f"{method} {url} (tentative {tentative + 1})")
                r = requests.request(method, url, **kwargs)
            except requests.Timeout:
                last_exception = BoostResellerError(
                    "Timeout : l'API n'a pas repondu.", code="timeout"
                )
            except requests.RequestException as e:
                last_exception = BoostResellerError(
                    f"Erreur reseau : {e}", code="network_error"
                )
            else:
                # Succes
                if r.status_code < 400:
                    try:
                        data = r.json()
                    except Exception:
                        raise BoostResellerError(
                            f"Reponse invalide (HTTP {r.status_code})",
                            code="invalid_response", status=r.status_code
                        )
                    if not data.get("success", False):
                        error = data.get("error", {})
                        raise BoostResellerError(
                            error.get("message", "Erreur API"),
                            code=error.get("code", "unknown_error"),
                            status=r.status_code, response=data
                        )
                    return data.get("data", {})

                # Erreur cote client : on ne retry PAS (sauf 429)
                if 400 <= r.status_code < 500 and r.status_code != 429:
                    try:
                        data = r.json()
                        error = data.get("error", {})
                    except Exception:
                        error = {}
                    raise BoostResellerError(
                        error.get("message", f"Erreur HTTP {r.status_code}"),
                        code=error.get("code", "http_error"),
                        status=r.status_code
                    )

                # 429 ou 5xx : on retry
                retry_after = r.headers.get("Retry-After")
                if r.status_code == 429:
                    last_exception = RateLimitError(
                        "Rate limit atteint.",
                        retry_after=int(retry_after) if retry_after else None
                    )
                else:
                    last_exception = BoostResellerError(
                        f"Erreur serveur (HTTP {r.status_code})",
                        code="server_error", status=r.status_code
                    )

            # Attente avant retry (backoff exponentiel)
            if tentative < self.max_retries:
                wait = min(2 ** tentative, 8)
                if isinstance(last_exception, RateLimitError) and last_exception.retry_after:
                    wait = last_exception.retry_after
                logger.debug(f"Retry dans {wait}s...")
                time.sleep(wait)

        raise last_exception or BoostResellerError("Erreur inconnue")

    # ─── Requetes personnalisees ──────────────────────────────

    def request(self, method, endpoint, **kwargs):
        """Envoie une requete personnalisee. Ex: client.request('GET', '/boutique')"""
        return self._request(method.upper(), endpoint, **kwargs)

    # ─── Helpers ──────────────────────────────────────────────

    def ping(self):
        """Verifie que la connexion a l'API fonctionne."""
        try:
            self.boutique.get()
            return True
        except BoostResellerError:
            return False

    def health(self):
        """Retourne un dict avec le statut de la connexion."""
        start = time.time()
        try:
            self.boutique.get()
            return {
                "ok": True,
                "duration_ms": round((time.time() - start) * 1000),
                "api_url": self.base_url,
                "version": __version__,
            }
        except BoostResellerError as e:
            return {
                "ok": False,
                "error": str(e),
                "code": e.code,
                "status": e.status,
                "duration_ms": round((time.time() - start) * 1000),
            }

    def __repr__(self):
        masked = self.api_key[:16] + "..." if self.api_key else "none"
        return f"<BoostReseller api_key={masked} base={self.base_url}>"