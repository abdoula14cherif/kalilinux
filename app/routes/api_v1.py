def api_key_required(scope_requis):
    """
    Decorateur qui verifie la cle API et le scope.
    SÉCURITÉ : refuse l'authentification par cookie de session.
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # ⚠️ SÉCURITÉ : NE JAMAIS accepter le cookie de session
            # Pour éviter CSRF via XSS
            from flask import session as flask_session
            if "user_id" in flask_session:
                # Un client avec session cookie essaie d'utiliser l'API
                # → On refuse pour éviter le CSRF
                return _erreur("use_api_key",
                              "L'API accepte uniquement les cles API (Bearer), pas les sessions",
                              401)

            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                return _erreur("missing_token", "Header Authorization manquant ou invalide", 401)

            full_key = auth_header.replace("Bearer ", "").strip()
            
            # ⚠️ Validation format strict
            import re
            if not re.match(r"^bsk_live_[A-Za-z0-9_\-]{20,}$", full_key):
                return _erreur("invalid_format", "Format de cle API invalide", 401)

            cle = verifier_cle(full_key)

            if not cle:
                return _erreur("invalid_token", "Cle API invalide ou revoquee", 401)

            if not cle_possede_scope(cle, scope_requis):
                return _erreur("forbidden_scope",
                              f"Votre cle ne possede pas le scope '{scope_requis}'",
                              403)

            profile = get_profile_by_slug_via_id(cle["revendeur_id"])
            if not profile:
                return _erreur("profile_not_found", "Revendeur introuvable", 404)

            # ⚠️ Verifie que le revendeur n'est pas banni
            if profile.get("banni"):
                return _erreur("account_suspended", "Compte suspendu", 403)

            kwargs["_profile"] = profile
            kwargs["_api_key"] = cle

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