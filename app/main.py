"""
AWS Resource Lifecycle Tracker — Dashboard (Flask)
Phase 0: Skeleton — health check and placeholder homepage only.
Full routes and templates added in Phase 6 & 7.
"""

import logging
import os

import psycopg2
from flask import Flask, jsonify, render_template_string
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash, generate_password_hash

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger("app.main")

app = Flask(__name__)
auth = HTTPBasicAuth()

DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")

if not DASHBOARD_PASSWORD:
    logger.warning(
        "DASHBOARD_PASSWORD is not set. "
        "Auth is disabled in Phase 0 but enforced from Phase 6."
    )

_password_hash = generate_password_hash(DASHBOARD_PASSWORD) if DASHBOARD_PASSWORD else None


@auth.verify_password
def verify_password(username, password):
    if not _password_hash:
        return username
    if username == DASHBOARD_USER and check_password_hash(_password_hash, password):
        return username
    return None


def _check_db_connection() -> bool:
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
        return True
    except Exception as e:
        logger.error(f"DB health check failed: {e}")
        return False


@app.route("/health")
def health():
    db_ok = _check_db_connection()
    status = "ok" if db_ok else "error"
    http_code = 200 if db_ok else 500
    return jsonify({"status": status, "db": "connected" if db_ok else "unreachable"}), http_code


@app.route("/")
@auth.login_required
def index():
    return render_template_string(PLACEHOLDER_HTML)


PLACEHOLDER_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS Resource Lifecycle Tracker</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
        }
        .card {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 48px;
            text-align: center;
            max-width: 480px;
        }
        h1 { color: #f8fafc; margin: 0 0 8px; font-size: 1.5rem; }
        p  { color: #94a3b8; margin: 0 0 24px; }
        .badge {
            display: inline-block;
            background: #0ea5e9;
            color: white;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 4px 12px;
            border-radius: 999px;
        }
        .check { color: #22c55e; font-size: 3rem; margin-bottom: 16px; }
    </style>
</head>
<body>
    <div class="card">
        <div class="check">&#10003;</div>
        <h1>AWS Resource Lifecycle Tracker</h1>
        <p>Phase 0 complete — infrastructure skeleton is running.</p>
        <p>Flask is up. Database is connected. Poller is running.</p>
        <span class="badge">PHASE 0 — SKELETON</span>
    </div>
</body>
</html>
"""


if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info("Starting Flask — debug: " + str(debug))
    logger.info("Dashboard: http://0.0.0.0:5000")
    logger.info("Health check: http://0.0.0.0:5000/health")
    app.run(host="0.0.0.0", port=5000, debug=debug)