"""
Factory Flask pour Boost Reseller.
SÉCURITÉ SÉVÈRE : headers, handler global, exclusions CSRF.
"""
import os
import logging
from flask import Flask, render_template, send_from_directory, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.exceptions import HTTPException
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per hour", "60 per minute"],
    headers_enabled=True,
)

csrf = CSRFProtect()


def create_app(config_name="production"):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    from app.config import config_map
    app.config.from_object(config_map[config_name])

    limiter.init_app(app)
    csrf.init_app(app)

    if app.config.get("RATELIMIT_STORAGE_URI"):
        limiter.storage_uri = app.config["RATELIMIT_STORAGE_URI"]

    # ─── Enregistrement des blueprints ────────────────────────
    from app.routes.home import home_bp
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.dashboard_shop import dashboard_shop_bp
    from app.routes.dashboard_dev import dashboard_dev_bp
    from app.routes.dashboard_admin import dashboard_admin_bp
    from app.routes.boutique import boutique_bp
    from app.routes.api_v1 import api_v1_bp
    from app.routes.webhooks import webhooks_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(dashboard_shop_bp, url_prefix="/dashboard")
    app.register_blueprint(dashboard_dev_bp, url_prefix="/dashboard/developpeur")
    app.register_blueprint(dashboard_admin_bp, url_prefix="/dashboard/admin")
    app.register_blueprint(boutique_bp)
    app.register_blueprint(api_v1_bp, url_prefix="/api/v1")
    app.register_blueprint(webhooks_bp, url_prefix="/webhooks")

    # ─── CSRF exempt pour les API et webhooks (auth par cle/signature) ───
    csrf.exempt(api_v1_bp)
    csrf.exempt(webhooks_bp)

    # ─── Fichiers statiques (PWA) ─────────────────────────────
    @app.route("/sw.js")
    def sw():
        return send_from_directory("static", "sw.js", mimetype="application/javascript")

    @app.route("/manifest.json")
    def manifest():
        return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

    # ─── Headers de securite renforces ────────────────────────
    @app.after_request
    def add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        if not app.debug:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "font-src 'self' https://cdnjs.cloudflare.com data:; "
            "img-src 'self' data: https: blob:; "
            "connect-src 'self' https://*.supabase.co https://*.supabase.in; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        if request.path.startswith(("/dashboard", "/auth", "/api/")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
        return response

    # ─── Gestion des erreurs ──────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not found"}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        logger.exception("Erreur 500")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def ratelimit_handler(e):
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "Trop de requetes. Reessayez plus tard.",
                "retry_after": getattr(e, "description", None)
            }), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
        logger.warning(f"[SECURITE] CSRF echec : {e.description} | IP={ip} | path={request.path}")
        if request.path.startswith("/api/"):
            return jsonify({"error": "CSRF token invalide ou manquant"}), 400
        return render_template("errors/400.html",
                              message="Session expiree, rechargez la page."), 400

    @app.errorhandler(Exception)
    def handle_exception(e):
        if isinstance(e, HTTPException):
            return e
        logger.exception(f"Exception non geree : {type(e).__name__}")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Erreur interne du serveur"}), 500
        return render_template("errors/500.html"), 500

    # ─── Logging ──────────────────────────────────────────────
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    return app