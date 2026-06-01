from flask import Blueprint, render_template
from flask_login import current_user

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
def index():
    return render_template("index.html", user=current_user if current_user.is_authenticated else None)


@dashboard_bp.route("/index")
def home():
    return render_template("index.html", user=current_user if current_user.is_authenticated else None)
