"""
API v1 publique — Utilise les clés API pour authentifier les requêtes.
"""
import logging
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from app.models.api_keys import verifier_cle, cle_possede_scope, log_utilisation
from app.models.database import (
    get_profile_by_slug, get_produits_revendeur, get_produit_boutique,
    create_produit_boutique, update_produit_boutique, delete_produit_boutique,
    get_commandes_boutique_revendeur, get_commande_boutique_by_reference,
    update_commande_boutique, get_revendeur_clients_detail,
    get_revendeur_orders, get_revendeur_gains_total, update_profile
)

logger = logging.getLogger(__name__)
api_v1_bp = Blueprint("api_v1", __name__)


def _erreur(code, message, http_status=400):
    return jsonify({
        "success": False,
        "error": {"code": code, "message": message}
    }), http_status


def _succes(data, http_status=200):
    return jsonify({"success": True, "data": data}), http_status


def api_key_required(scope_requis):
    """Decorateur qui verifie la cle API et le scope."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return _erreur("missing_token", "Header Authorization manquant ou invalide", 401)

            full_key = auth_header.replace("Bearer ", "").strip()
            cle = verifier_cle(full_key)

            if not cle:
                return _erreur("invalid_token", "Cle API invalide ou revoquee", 401)

            if not cle_possede_scope(cle, scope_requis):
                return _erreur("forbidden_scope",
                              f"Votre cle ne possede pas le scope '{scope_requis}'",
                              403)

            # Charger le profile du revendeur
            profile = get_profile_by_slug_via_id(cle["revendeur_id"])
            if not profile:
                return _erreur("profile_not_found", "Revendeur introuvable", 404)

            # Injecter dans kwargs
            kwargs["_profile"] = profile
            kwargs["_api_key"] = cle

            # Log utilisation (best effort)
            try:
                log_utilisation(
                    cle["id"],
                    request.path,
                    request.method,
                    200,
                    request.remote_addr
                )
            except Exception:
                pass

            return f(*args, **kwargs)
        return wrapper
    return decorator


def get_profile_by_slug_via_id(revendeur_id):
    """Recupere un profile par son ID (sans slug)."""
    from app.models.database import _url, _headers
    import requests
    try:
        r = requests.get(
            _url(f"profiles?id=eq.{revendeur_id}&limit=1"),
            headers=_headers(True),
            timeout=10
        )
        data = r.json()
        return data[0] if isinstance(data, list) and data else None
    except Exception as e:
        logger.error(f"get_profile_by_slug_via_id: {type(e).__name__}")
        return None


# ═══════════════════════════════════════════════════════════════
# BOUTIQUE
# ═══════════════════════════════════════════════════════════════

@api_v1_bp.route("/boutique", methods=["GET"])
@api_key_required("boutique:read")
def get_boutique(_profile=None, _api_key=None):
    try:
        revenus = 0
        try:
            orders = get_revendeur_orders(_profile["id"], limit=500)
            revenus = sum(o.get("prix_total", 0) or 0 for o in orders if o.get("statut") == "termine")
        except Exception:
            pass

        nb_produits = 0
        try:
            nb_produits = len(get_produits_revendeur(_profile["id"]))
        except Exception:
            pass

        nb_commandes = 0
        try:
            nb_commandes = len(get_commandes_boutique_revendeur(_profile["id"], limit=500))
        except Exception:
            pass

        return _succes({
            "nom": _profile.get("boutique_nom"),
            "slug": _profile.get("revendeur_slug"),
            "slogan": _profile.get("boutique_slogan"),
            "message_accueil": _profile.get("boutique_message_accueil"),
            "statut": "en_ligne" if _profile.get("boutique_active") else "en_pause",
            "est_revendeur": _profile.get("est_revendeur", False),
            "whatsapp": _profile.get("boutique_whatsapp"),
            "email": _profile.get("boutique_email"),
            "facebook": _profile.get("boutique_facebook"),
            "instagram": _profile.get("boutique_instagram"),
            "tiktok": _profile.get("boutique_tiktok"),
            "logo_url": _profile.get("boutique_logo_url"),
            "theme": _profile.get("boutique_theme"),
            "type_boutique": _profile.get("boutique_type"),
            "nb_produits": nb_produits,
            "nb_commandes": nb_commandes,
            "revenus_total": revenus,
            "visiteurs": _profile.get("boutique_visites") or 0,
        })
    except Exception as e:
        logger.error(f"api get_boutique: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


@api_v1_bp.route("/boutique", methods=["PATCH"])
@api_key_required("boutique:write")
def patch_boutique(_profile=None, _api_key=None):
    try:
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return _erreur("invalid_body", "Body JSON invalide", 400)

        autorises = {
            "nom": 60, "slogan": 100, "message_accueil": 300,
            "whatsapp": 30, "email": 150, "facebook": 300,
            "instagram": 300, "tiktok": 300, "telegram": 300,
            "a_propos": 1000,
        }
        updates = {}
        for champ, maxlen in autorises.items():
            if champ in data:
                valeur = data[champ]
                if valeur is None:
                    updates[f"boutique_{champ}"] = None
                elif isinstance(valeur, str):
                    updates[f"boutique_{champ}"] = valeur.strip()[:maxlen] or None

        if not updates:
            return _erreur("no_changes", "Aucun champ valide à mettre à jour", 400)

        ok = update_profile(_profile["id"], updates)
        if ok:
            return _succes({"message": "Boutique mise à jour", "champs_modifies": list(updates.keys())})
        return _erreur("update_failed", "Erreur lors de la mise à jour", 500)
    except Exception as e:
        logger.error(f"api patch_boutique: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


# ═══════════════════════════════════════════════════════════════
# PRODUITS
# ═══════════════════════════════════════════════════════════════

@api_v1_bp.route("/produits", methods=["GET"])
@api_key_required("produits:read")
def list_produits(_profile=None, _api_key=None):
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
        actif_filter = request.args.get("actif")
        cat_filter = request.args.get("categorie_id")

        produits = get_produits_revendeur(_profile["id"])

        if actif_filter is not None:
            actif_bool = actif_filter.lower() == "true"
            produits = [p for p in produits if bool(p.get("actif")) == actif_bool]
        if cat_filter:
            produits = [p for p in produits if str(p.get("categorie_id")) == str(cat_filter)]

        total = len(produits)
        produits = produits[offset:offset + limit]

        return _succes({
            "total": total,
            "limit": limit,
            "offset": offset,
            "produits": [{
                "id": p.get("id"),
                "nom": p.get("nom"),
                "description": p.get("description"),
                "prix": p.get("prix"),
                "stock": p.get("stock"),
                "image_url": p.get("image_url"),
                "categorie_id": p.get("categorie_id"),
                "actif": p.get("actif"),
                "created_at": p.get("created_at"),
            } for p in produits]
        })
    except Exception as e:
        logger.error(f"api list_produits: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


@api_v1_bp.route("/produits/<produit_id>", methods=["GET"])
@api_key_required("produits:read")
def get_produit(produit_id, _profile=None, _api_key=None):
    try:
        p = get_produit_boutique(produit_id)
        if not p or p.get("revendeur_id") != _profile["id"]:
            return _erreur("not_found", "Produit introuvable", 404)
        return _succes({
            "id": p.get("id"),
            "nom": p.get("nom"),
            "description": p.get("description"),
            "prix": p.get("prix"),
            "stock": p.get("stock"),
            "image_url": p.get("image_url"),
            "categorie_id": p.get("categorie_id"),
            "actif": p.get("actif"),
            "created_at": p.get("created_at"),
        })
    except Exception as e:
        logger.error(f"api get_produit: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


@api_v1_bp.route("/produits", methods=["POST"])
@api_key_required("produits:write")
def create_produit(_profile=None, _api_key=None):
    try:
        data = request.get_json(silent=True) or {}
        nom = (data.get("nom") or "").strip()[:100]
        if not nom:
            return _erreur("invalid_nom", "Le nom est obligatoire", 400)

        try:
            prix = float(data.get("prix", 0))
            if prix < 0 or prix > 100000000:
                raise ValueError
        except Exception:
            return _erreur("invalid_prix", "Prix invalide", 400)

        nouveau = {
            "revendeur_id": _profile["id"],
            "nom": nom,
            "description": (data.get("description") or "").strip()[:1000] or None,
            "prix": prix,
            "actif": True,
        }

        if data.get("stock") is not None:
            try:
                nouveau["stock"] = int(data["stock"])
            except Exception:
                pass

        if data.get("categorie_id"):
            try:
                nouveau["categorie_id"] = int(data["categorie_id"])
            except Exception:
                pass

        result = create_produit_boutique(nouveau)
        if result:
            return _succes({
                "id": result.get("id"),
                "nom": result.get("nom"),
                "prix": result.get("prix"),
                "message": "Produit créé"
            }, 201)
        return _erreur("create_failed", "Erreur de création", 500)
    except Exception as e:
        logger.error(f"api create_produit: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


@api_v1_bp.route("/produits/<produit_id>", methods=["PATCH"])
@api_key_required("produits:write")
def patch_produit(produit_id, _profile=None, _api_key=None):
    try:
        p = get_produit_boutique(produit_id)
        if not p or p.get("revendeur_id") != _profile["id"]:
            return _erreur("not_found", "Produit introuvable", 404)

        data = request.get_json(silent=True) or {}
        updates = {}

        if "nom" in data:
            nom = (data["nom"] or "").strip()[:100]
            if nom:
                updates["nom"] = nom
        if "description" in data:
            updates["description"] = (data["description"] or "").strip()[:1000] or None
        if "prix" in data:
            try:
                prix = float(data["prix"])
                if 0 <= prix <= 100000000:
                    updates["prix"] = prix
            except Exception:
                pass
        if "stock" in data:
            try:
                updates["stock"] = int(data["stock"])
            except Exception:
                pass
        if "actif" in data:
            updates["actif"] = bool(data["actif"])
        if "categorie_id" in data:
            try:
                updates["categorie_id"] = int(data["categorie_id"])
            except Exception:
                pass

        if not updates:
            return _erreur("no_changes", "Aucun champ valide", 400)

        ok = update_produit_boutique(produit_id, updates)
        if ok:
            return _succes({"message": "Produit mis à jour", "champs": list(updates.keys())})
        return _erreur("update_failed", "Erreur", 500)
    except Exception as e:
        logger.error(f"api patch_produit: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


@api_v1_bp.route("/produits/<produit_id>", methods=["DELETE"])
@api_key_required("produits:write")
def delete_produit(produit_id, _profile=None, _api_key=None):
    try:
        p = get_produit_boutique(produit_id)
        if not p or p.get("revendeur_id") != _profile["id"]:
            return _erreur("not_found", "Produit introuvable", 404)

        ok = delete_produit_boutique(produit_id)
        if ok:
            return _succes({"message": "Produit supprimé"})
        return _erreur("delete_failed", "Erreur", 500)
    except Exception as e:
        logger.error(f"api delete_produit: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


# ═══════════════════════════════════════════════════════════════
# COMMANDES
# ═══════════════════════════════════════════════════════════════

@api_v1_bp.route("/commandes", methods=["GET"])
@api_key_required("commandes:read")
def list_commandes(_profile=None, _api_key=None):
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
        statut = request.args.get("statut")

        commandes = get_commandes_boutique_revendeur(_profile["id"], limit=500)

        if statut:
            commandes = [c for c in commandes if c.get("statut") == statut]

        total = len(commandes)
        commandes = commandes[offset:offset + limit]

        return _succes({
            "total": total,
            "limit": limit,
            "offset": offset,
            "commandes": [{
                "reference": c.get("reference"),
                "client_nom": c.get("client_nom"),
                "client_telephone": c.get("client_telephone"),
                "client_email": c.get("client_email"),
                "total": c.get("total"),
                "statut": c.get("statut"),
                "mode_paiement": c.get("mode_paiement"),
                "produits": c.get("produits") or [],
                "created_at": c.get("created_at"),
            } for c in commandes]
        })
    except Exception as e:
        logger.error(f"api list_commandes: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


@api_v1_bp.route("/commandes/<reference>", methods=["GET"])
@api_key_required("commandes:read")
def get_commande(reference, _profile=None, _api_key=None):
    try:
        c = get_commande_boutique_by_reference(reference)
        if not c or c.get("revendeur_id") != _profile["id"]:
            return _erreur("not_found", "Commande introuvable", 404)
        return _succes({
            "reference": c.get("reference"),
            "client_nom": c.get("client_nom"),
            "client_telephone": c.get("client_telephone"),
            "client_email": c.get("client_email"),
            "client_adresse": c.get("client_adresse"),
            "client_ville": c.get("client_ville"),
            "produits": c.get("produits") or [],
            "sous_total": c.get("sous_total"),
            "frais_livraison": c.get("frais_livraison"),
            "total": c.get("total"),
            "mode_paiement": c.get("mode_paiement"),
            "statut": c.get("statut"),
            "note_client": c.get("note_client"),
            "created_at": c.get("created_at"),
        })
    except Exception as e:
        logger.error(f"api get_commande: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


@api_v1_bp.route("/commandes/<reference>", methods=["PATCH"])
@api_key_required("commandes:write")
def patch_commande(reference, _profile=None, _api_key=None):
    try:
        c = get_commande_boutique_by_reference(reference)
        if not c or c.get("revendeur_id") != _profile["id"]:
            return _erreur("not_found", "Commande introuvable", 404)

        data = request.get_json(silent=True) or {}
        statut = data.get("statut")
        valides = ("en_attente", "confirmee", "en_livraison", "livree", "annulee")
        if statut not in valides:
            return _erreur("invalid_statut", f"Statut invalide. Valides : {', '.join(valides)}", 400)

        ok = update_commande_boutique(c["id"], {"statut": statut})
        if ok:
            return _succes({"message": "Commande mise à jour", "statut": statut})
        return _erreur("update_failed", "Erreur", 500)
    except Exception as e:
        logger.error(f"api patch_commande: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


# ═══════════════════════════════════════════════════════════════
# CLIENTS
# ═══════════════════════════════════════════════════════════════

@api_v1_bp.route("/clients", methods=["GET"])
@api_key_required("clients:read")
def list_clients(_profile=None, _api_key=None):
    try:
        limit = min(int(request.args.get("limit", 50)), 200)
        clients = get_revendeur_clients_detail(_profile["id"])
        total = len(clients)
        clients = clients[:limit]
        return _succes({
            "total": total,
            "clients": [{
                "id": c.get("id"),
                "email": c.get("email"),
                "full_name": c.get("full_name"),
                "country": c.get("country"),
                "balance": c.get("balance"),
                "rattache_le": c.get("rattache_le"),
            } for c in clients]
        })
    except Exception as e:
        logger.error(f"api list_clients: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)


# ═══════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════

@api_v1_bp.route("/stats", methods=["GET"])
@api_key_required("stats:read")
def get_stats(_profile=None, _api_key=None):
    try:
        periode = request.args.get("periode", "all")

        commandes = get_commandes_boutique_revendeur(_profile["id"], limit=500)
        commandes_livrees = [c for c in commandes if c.get("statut") == "livree"]

        revenus = sum(c.get("total", 0) or 0 for c in commandes_livrees)
        nb_clients = 0
        try:
            nb_clients = len(get_revendeur_clients_detail(_profile["id"]))
        except Exception:
            pass

        # Top produits
        compteur = {}
        for c in commandes_livrees:
            for p in c.get("produits") or []:
                nom = p.get("nom", "Inconnu")
                compteur[nom] = compteur.get(nom, 0) + p.get("qte", 1)

        top_produits = sorted(
            [{"nom": k, "ventes": v} for k, v in compteur.items()],
            key=lambda x: x["ventes"], reverse=True
        )[:10]

        visiteurs = _profile.get("boutique_visites") or 0
        taux_conv = round((len(commandes) / visiteurs * 100), 2) if visiteurs > 0 else 0

        return _succes({
            "periode": periode,
            "nb_commandes": len(commandes),
            "nb_commandes_livrees": len(commandes_livrees),
            "revenus": revenus,
            "nb_clients": nb_clients,
            "visiteurs": visiteurs,
            "taux_conversion": taux_conv,
            "top_produits": top_produits,
        })
    except Exception as e:
        logger.error(f"api get_stats: {type(e).__name__}")
        return _erreur("server_error", "Erreur serveur", 500)