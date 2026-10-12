import os
import logging
from flask import Flask, render_template, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv

load_dotenv()

limiter = Limiter(key_func=get_remote_address, default_limits=["200 per hour"])
csrf = CSRFProtect()


def create_app(config_name="production"):
    app = Flask(__name__, template_folder="templates", static_folder="static")

    from app.config import config_map
    app.config.from_object(config_map[config_name])

    limiter.init_app(app)
    csrf.init_app(app)

    from app.routes.home import home_bp
    app.register_blueprint(home_bp)

    @app.route("/sw.js")
    def sw():
        return send_from_directory("static", "sw.js", mimetype="application/javascript")

    @app.route("/manifest.json")
    def manifest():
        return send_from_directory("static", "manifest.json", mimetype="application/manifest+json")

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(e):
        return render_template("errors/500.html"), 500

    logging.basicConfig(level=logging.INFO)

    return app