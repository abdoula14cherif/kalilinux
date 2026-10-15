"""
Boost Reseller - Mini SDK Python
================================
Client Python officiel pour l'API Boost Reseller.

Installation :
    pip install requests

Utilisation :
    from boost_reseller import BoostReseller

    client = BoostReseller(api_key="bsk_live_xxxx")

    # Boutique
    boutique = client.boutique.get()
    print(boutique["nom"])

    # Produits
    produits = client.produits.list(limit=20)
    client.produits.create(nom="T-shirt", prix=5000, stock=100)

    # Commandes
    commandes = client.commandes.list(statut="en_attente")
    client.commandes.update("CMD-ABC123", statut="livree")

    # Stats
    stats = client.stats.get(periode="30j")
    print(stats["revenus"])

Version : 1.0.0
Licence : MIT
"""

import requests


__version__ = "1.0.0"


class BoostResellerError(Exception):
    """Erreur renvoyee par l'API Boost Reseller."""
    def __init__(self, message, code=None, status=None):
        super().__init__(message)
        self.code = code
        self.status = status


class _BaseResource:
    def __init__(self, client):
        self._client = client

    def _request(self, method, endpoint, **kwargs):
        return self._client._request(method, endpoint, **kwargs)


class BoutiqueResource(_BaseResource):
    def get(self):
        """Recupere les informations de la boutique."""
        return self._request("GET", "/boutique")

    def update(self, **champs):
        """Met a jour les champs de la boutique (nom, slogan, whatsapp...)."""
        return self._request("PATCH", "/boutique", json=champs)


class ProduitsResource(_BaseResource):
    def list(self, limit=50, offset=0, actif=None, categorie_id=None):
        """Liste les produits avec pagination et filtres."""
        params = {"limit": limit, "offset": offset}
        if actif is not None:
            params["actif"] = "true" if actif else "false"
        if categorie_id is not None:
            params["categorie_id"] = categorie_id
        return self._request("GET", "/produits", params=params).get("produits", [])

    def get(self, produit_id):
        """Recupere un produit par son ID."""
        return self._request("GET", f"/produits/{produit_id}")

    def create(self, nom, prix, description=None, stock=None, categorie_id=None):
        """Cree un nouveau produit."""
        payload = {"nom": nom, "prix": prix}
        if description is not None:
            payload["description"] = description
        if stock is not None:
            payload["stock"] = stock
        if categorie_id is not None:
            payload["categorie_id"] = categorie_id
        return self._request("POST", "/produits", json=payload)

    def update(self, produit_id, **champs):
        """Met a jour un produit existant."""
        return self._request("PATCH", f"/produits/{produit_id}", json=champs)

    def delete(self, produit_id):
        """Supprime un produit."""
        return self._request("DELETE", f"/produits/{produit_id}")


class CommandesResource(_BaseResource):
    def list(self, limit=50, offset=0, statut=None):
        """Liste les commandes."""
        params = {"limit": limit, "offset": offset}
        if statut:
            params["statut"] = statut
        return self._request("GET", "/commandes", params=params).get("commandes", [])

    def get(self, reference):
        """Recupere une commande par sa reference."""
        return self._request("GET", f"/commandes/{reference}")

    def update(self, reference, statut):
        """Met a jour le statut d'une commande."""
        return self._request("PATCH", f"/commandes/{reference}", json={"statut": statut})


class ClientsResource(_BaseResource):
    def list(self, limit=50):
        """Liste les clients inscrits sur votre boutique."""
        return self._request("GET", "/clients", params={"limit": limit}).get("clients", [])


class StatsResource(_BaseResource):
    def get(self, periode="all"):
        """Recupere les statistiques (periode : 7j, 30j, 90j, 1an, all)."""
        return self._request("GET", "/stats", params={"periode": periode})


class BoostReseller:
    """
    Client principal pour l'API Boost Reseller.

    Args:
        api_key (str): Votre cle API (format bsk_live_xxxx)
        base_url (str): URL de base de l'API (defaut : production)
        timeout (int): Timeout des requetes en secondes (defaut : 30)
    """

    DEFAULT_BASE_URL = "https://reseller.boostcentral.world/api/v1"

    def __init__(self, api_key, base_url=None, timeout=30):
        if not api_key or not api_key.startswith("bsk_live_"):
            raise BoostResellerError(
                "Cle API invalide. Format attendu : bsk_live_xxxx",
                code="invalid_api_key"
            )
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout

        self.boutique = BoutiqueResource(self)
        self.produits = ProduitsResource(self)
        self.commandes = CommandesResource(self)
        self.clients = ClientsResource(self)
        self.stats = StatsResource(self)

    def _request(self, method, endpoint, **kwargs):
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        kwargs.setdefault("timeout", self.timeout)
        kwargs["headers"] = headers

        try:
            r = requests.request(method, url, **kwargs)
        except requests.Timeout:
            raise BoostResellerError("Timeout : l'API n'a pas repondu.", code="timeout")
        except requests.RequestException as e:
            raise BoostResellerError(f"Erreur reseau : {e}", code="network_error")

        try:
            data = r.json()
        except Exception:
            raise BoostResellerError(
                f"Reponse invalide (HTTP {r.status_code})",
                code="invalid_response",
                status=r.status_code
            )

        if r.status_code >= 400 or not data.get("success", False):
            error = data.get("error", {})
            raise BoostResellerError(
                error.get("message", f"Erreur HTTP {r.status_code}"),
                code=error.get("code", "unknown_error"),
                status=r.status_code
            )

        return data.get("data", {})

    def ping(self):
        """Verifie que la connexion a l'API fonctionne."""
        try:
            self.boutique.get()
            return True
        except BoostResellerError:
            return False