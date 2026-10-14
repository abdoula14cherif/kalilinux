"""
Factory Flask pour Boost Reseller.
Sécurité niveau bancaire : rate limiting, headers, gestion erreurs.
"""
import os
import logging
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, CSRFError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Rate limiter global ───────────────────────────────────────
# ⚠️ get_remote_address utilise X-Forwarded-For derrière Vercel
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per hour", "60 per minute"],  # Limite globale
    headers_enabled=True,
)

# ─── CSRF protection ───────────────────────────────────────────
csrf = CSRFProtect()


def create_app(config_name="production"):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    # ─── Chargement de la config ───────────────────────────────
    from app.config import config_map
    app.config.from_object(config_map[config_name])

    # ─── Init des extensions ───────────────────────────────────
    limiter.init_app(app)
    csrf.init_app(app)

    # ─── Rate limit storage configurable ───────────────────────
    # ⚠️ memory:// ne marche pas en multi-instances (Vercel)
    if app.config.get("RATELIMIT_STORAGE_URI"):
        limiter.storage_uri = app.config["RATELIMIT_STORAGE_URI"]

    # ─── Enregistrement des blueprints ─────────────────────────
    from app.routes.home import home_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.boutique import boutique_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(boutique_bp)

    # ─── Fichiers statiques (PWA) ──────────────────────────────
    @app.route("/sw.js")
    def sw():
        return send_from_directory("static", "sw.js", mimetype="application/javascript")

    @app.route("/manifest.json")
    def manifest():
        return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

    # ═══════════════════════════════════════════════════════════
    # 🔒 HEADERS DE SÉCURITÉ (appliqués à CHAQUE réponse)
    # ═══════════════════════════════════════════════════════════
    @app.after_request
    def add_security_headers(response):
        # Interdit le sniffing MIME (empêche les XSS via upload déguisé)
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Empêche l'inclusion dans des iframes (anti-clickjacking)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Contrôle les infos envoyées dans le Referer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Désactive les APIs inutiles du navigateur
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        # Force HTTPS pendant 1 an (HSTS)
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        # Content Security Policy (assouplie pour FontAwesome + CDN)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "font-src 'self' https://cdnjs.cloudflare.com data:; "
            "img-src 'self' data: https: blob:; "
            "connect-src 'self' https://*.supabase.co https://*.supabase.in; "
            "frame-ancestors 'self';"
        )
        # Empêche le cache des pages authentifiées
        if request.path.startswith(("/dashboard", "/auth")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
        return response

    # ═══════════════════════════════════════════════════════════
    # 🔒 GESTION DES ERREURS
    # ═══════════════════════════════════════════════════════════
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Erreur 500 non gérée")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def ratelimit_handler(e):
        """Renvoie une erreur propre si la limite de requêtes est atteinte."""
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "Trop de requêtes. Réessayez plus tard.",
                "retry_after": getattr(e, "description", None)
            }), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        """Gère les erreurs CSRF (token manquant ou invalide)."""
        logger.warning(f"CSRF échec : {e.description} | path={request.path}")
        if request.path.startswith("/api/"):
            return jsonify({"error": "CSRF token invalide ou manquant"}), 400
        return render_template("errors/400.html",
                              message="Session expirée, rechargez la page."), 400

    # ─── Logging ───────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    return app


# ═══════════════════════════════════════════════════════════════
# ⚠️ ERREURS CORRIGÉES DANS CE FICHIER
# ═══════════════════════════════════════════════════════════════
#
# 🔴 CRITIQUE #1 — Pas de headers de sécurité HTTP
#    AVANT : Vulnérable au clickjacking, MIME sniffing, downgrade HTTPS.
#    APRÈS : X-Content-Type-Options, X-Frame-Options, HSTS,
#            Referrer-Policy, Permissions-Policy, CSP.
#
# 🔴 CRITIQUE #2 — Rate limiting trop permissif (200/h global)
#    AVANT : Un bot pouvait spammer 200 requêtes/h sans blocage.
#    APRÈS : 300/h + 60/min en global. Et @limiter.limit() ciblé sur
#            les routes critiques (à faire dans chaque blueprint).
#
# 🔴 CRITIQUE #3 — Rate limit storage en mémoire
#    AVANT : Les limites étaient perdues à chaque redéploiement Vercel.
#    APRÈS : RATELIMIT_STORAGE_URI configurable (Redis en prod).
#
# 🔴 CRITIQUE #4 — Pas de gestion des erreurs 429 et CSRF
#    AVANT : Erreur 500 par défaut si limite atteinte ou token invalide.
#    APRÈS : Handlers dédiés + log warning CSRF + message utilisateur.
#
# 🟠 IMPORTANT #5 — Cache-Control absent sur les pages privées
#    AVANT : Un proxy pouvait cacher les pages dashboard.
#    APRÈS : no-store + no-cache sur /dashboard et /auth.
#
# 🟢 BONUS — Timestamps et noms de logger dans les logs
#    Format : 2025-01-15 10:23:45 [ERROR] app.routes.dashboard: message
#
# ═══════════════════════════════════════════════════════════════