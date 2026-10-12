import logging
from flask import Blueprint, render_template

logger = logging.getLogger(__name__)
home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def index():
    return render_template("index.html")


@home_bp.route("/health")
def health():
    return {"status": "ok", "service": "boost-reseller"}, 200