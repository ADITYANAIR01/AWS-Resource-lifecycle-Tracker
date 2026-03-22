"""
AWS Resource Lifecycle Tracker — Flask Dashboard
Phase 7: Full UI with templates, static files, auth enforcement.
"""

import logging
import os

import psycopg2
from flask import Flask, jsonify
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash, generate_password_hash

from db.connection import init_pool, release_connection
from routes.overview import overview_bp
from routes.resources import resources_bp
from routes.alerts import alerts_bp
from routes.poller import poller_bp

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("app.main")

app  = Flask(__name__, static_folder="static", template_folder="templates")
auth = HTTPBasicAuth()

DASHBOARD_USER     = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

if not DASHBOARD_PASSWORD:
    logger.warning("DASHBOARD_PASSWORD not set — routes unprotected in dev mode")

_password_hash = (
    generate_password_hash(DASHBOARD_PASSWORD)
    if DASHBOARD_PASSWORD else None
)


@auth.verify_password
def verify_password(username, password):
    if not _password_hash:
        return username
    if username == DASHBOARD_USER and check_password_hash(_password_hash, password):
        return username
    return None


@app.teardown_appcontext
def teardown_db(exception):
    release_connection(exception)


app.register_blueprint(overview_bp)
app.register_blueprint(resources_bp)
app.register_blueprint(alerts_bp)
app.register_blueprint(poller_bp)


@app.before_request
def require_auth():
    from flask import request
    if request.path == "/health":
        return None
    if request.path.startswith("/static/"):
        return None
    return auth.login_required(lambda: None)()


@app.route("/health")
def health():
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", 5432)),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            connect_timeout=5,
        )
        conn.close()
        return jsonify({"status": "ok", "db": "connected"}), 200
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return jsonify({"status": "error", "db": "unreachable"}), 500


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    init_pool()
    logger.info("Dashboard: http://0.0.0.0:5000")
    logger.info("Health:    http://0.0.0.0:5000/health")
    app.run(host="0.0.0.0", port=5000, debug=debug)