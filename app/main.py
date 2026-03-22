"""
AWS Resource Lifecycle Tracker — Flask Dashboard
Phase 6: Full backend with all API routes, auth enforcement, health check.
"""

import logging
import os

import psycopg2
from flask import Flask, jsonify
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash, generate_password_hash

from db.connection import close_pool, init_pool, release_connection
from routes.overview import overview_bp
from routes.resources import resources_bp
from routes.alerts import alerts_bp
from routes.poller import poller_bp

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("app.main")

# ---------------------------------------------------------------------------
# Flask + Auth
# ---------------------------------------------------------------------------
app  = Flask(__name__)
auth = HTTPBasicAuth()

DASHBOARD_USER     = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

if not DASHBOARD_PASSWORD:
    logger.warning(
        "DASHBOARD_PASSWORD is not set — all routes are unprotected. "
        "Set DASHBOARD_PASSWORD in .env immediately."
    )

_password_hash = (
    generate_password_hash(DASHBOARD_PASSWORD)
    if DASHBOARD_PASSWORD else None
)


@auth.verify_password
def verify_password(username, password):
    if not _password_hash:
        # No password set — allow in dev mode with warning
        return username
    if username == DASHBOARD_USER and check_password_hash(
        _password_hash, password
    ):
        return username
    return None


# ---------------------------------------------------------------------------
# DB teardown — releases connection back to pool after every request
# ---------------------------------------------------------------------------
@app.teardown_appcontext
def teardown_db(exception):
    release_connection(exception)


# ---------------------------------------------------------------------------
# Blueprints — protected by auth
# ---------------------------------------------------------------------------
app.register_blueprint(overview_bp)
app.register_blueprint(resources_bp)
app.register_blueprint(alerts_bp)
app.register_blueprint(poller_bp)


# Apply auth to all blueprint routes
@app.before_request
def require_auth():
    from flask import request
    # Health check is always public — monitoring tools need it
    if request.path == "/health":
        return None
    return auth.login_required(lambda: None)()


# ---------------------------------------------------------------------------
# Health check — always public, no auth
# ---------------------------------------------------------------------------
@app.route("/health")
def health():
    """
    Health check — confirms app is running and DB is reachable.
    Used by CloudFormation cfn-signal in Phase 9.
    Returns 200 if healthy, 500 if DB unreachable.
    """
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


# ---------------------------------------------------------------------------
# Phase 0 placeholder — still serves at / until Phase 7 adds real templates
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>AWS Resource Lifecycle Tracker</title>
    <style>
        body { font-family: sans-serif; background: #0f172a;
               color: #e2e8f0; display: flex; align-items: center;
               justify-content: center; min-height: 100vh; margin: 0; }
        .card { background: #1e293b; border: 1px solid #334155;
                border-radius: 12px; padding: 48px; text-align: center; }
        h1 { color: #f8fafc; }
        p  { color: #94a3b8; }
        .badge { background: #0ea5e9; color: white; padding: 4px 12px;
                 border-radius: 999px; font-size: 0.75rem; }
        a { color: #38bdf8; }
    </style>
    </head>
    <body><div class="card">
        <h1>AWS Resource Lifecycle Tracker</h1>
        <p>Backend running. API endpoints available.</p>
        <p>
            <a href="/api/overview">/api/overview</a> &nbsp;|&nbsp;
            <a href="/api/resources">/api/resources</a> &nbsp;|&nbsp;
            <a href="/api/alerts">/api/alerts</a> &nbsp;|&nbsp;
            <a href="/api/poller">/api/poller</a>
        </p>
        <span class="badge">PHASE 6 — BACKEND</span>
    </div></body>
    </html>
    """, 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # Initialise DB pool before serving any requests
    init_pool()

    logger.info("Dashboard: http://0.0.0.0:5000")
    logger.info("Health:    http://0.0.0.0:5000/health")
    logger.info("API:       http://0.0.0.0:5000/api/overview")

    app.run(host="0.0.0.0", port=5000, debug=debug)