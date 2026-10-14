"""
Fonctions de sérialisation : convertit les données brutes (Supabase)
en version "safe" pour le frontend (masque les colonnes sensibles).
"""


def produit_safe(p):
    """Version safe d'un produit pour le template (sans colonnes internes)."""
    if not p:
        return {}
    return {
        "id": p.get("id"),
        "nom": p.get("nom"),
        "description": p.get("description"),
        "prix": p.get("prix"),
        "image_url": p.get("image_url"),
        "stock": p.get("stock"),
        "categorie_id": p.get("categorie_id"),
        "actif": p.get("actif"),
        "ordre": p.get("ordre"),
    }


def banniere_safe(b):
    """Version safe d'une bannière."""
    if not b:
        return {}
    return {
        "id": b.get("id"),
        "titre": b.get("titre"),
        "sous_titre": b.get("sous_titre"),
        "image_url": b.get("image_url"),
        "lien": b.get("lien"),
        "actif": b.get("actif"),
        "ordre": b.get("ordre"),
    }


def attribut_safe(a):
    """Version safe d'un attribut."""
    if not a:
        return {}
    return {
        "id": a.get("id"),
        "nom": a.get("nom"),
        "type": a.get("type"),
        "valeurs": a.get("valeurs") or [],
        "obligatoire": a.get("obligatoire"),
        "actif": a.get("actif"),
    }


def avis_safe(a):
    """Version safe d'un avis."""
    if not a:
        return {}
    return {
        "id": a.get("id"),
        "client_nom": a.get("client_nom"),
        "note": a.get("note"),
        "commentaire": a.get("commentaire"),
        "approuve": a.get("approuve"),
        "created_at": a.get("created_at"),
    }


def coupon_safe(c):
    """Version safe d'un coupon."""
    if not c:
        return {}
    return {
        "id": c.get("id"),
        "code": c.get("code"),
        "type": c.get("type"),
        "valeur": c.get("valeur"),
        "montant_min": c.get("montant_min"),
        "max_utilisations": c.get("max_utilisations"),
        "utilisations": c.get("utilisations"),
        "date_expiration": c.get("date_expiration"),
        "actif": c.get("actif"),
    }


def categorie_safe(c):
    """Version safe d'une catégorie."""
    if not c:
        return {}
    return {
        "id": c.get("id"),
        "nom": c.get("nom"),
        "description": c.get("description"),
        "type_code": c.get("type_code"),
        "ordre": c.get("ordre"),
    }


def commande_safe(c):
    """Version safe d'une commande."""
    if not c:
        return {}
    return {
        "id": c.get("id"),
        "reference": c.get("reference"),
        "client_nom": c.get("client_nom"),
        "client_email": c.get("client_email"),
        "client_telephone": c.get("client_telephone"),
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
    }