from flask import Blueprint, jsonify, render_template
from psycopg2.extras import RealDictCursor
from db.connection import get_connection

overview_bp = Blueprint("overview", __name__)


@overview_bp.route("/")
def index():
    return render_template("overview.html", active_page="overview")


@overview_bp.route("/api/overview")
def get_overview():
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute("""
                SELECT resource_type, COUNT(*) as count
                FROM resources WHERE is_active = TRUE
                GROUP BY resource_type ORDER BY count DESC
            """)
            resources_by_type = [dict(r) for r in cur.fetchall()]
            total_resources = sum(r["count"] for r in resources_by_type)

            cur.execute("""
                SELECT severity, COUNT(*) as count FROM alerts
                WHERE resolved_at IS NULL GROUP BY severity
            """)
            alerts_by_severity = {row["severity"]: row["count"] for row in cur.fetchall()}
            total_alerts = sum(alerts_by_severity.values())

            cur.execute("""
                SELECT COALESCE(SUM(estimated_cost_usd), 0) as total
                FROM resources WHERE is_active = TRUE
            """)
            total_cost = float(cur.fetchone()["total"])

            cur.execute("""
                SELECT id, status, started_at, completed_at,
                       resources_found, alerts_triggered, error_log
                FROM poller_runs ORDER BY started_at DESC LIMIT 1
            """)
            row = cur.fetchone()
            last_run = None
            if row:
                last_run = dict(row)
                if last_run.get("started_at"):
                    last_run["started_at"] = last_run["started_at"].isoformat()
                if last_run.get("completed_at"):
                    last_run["completed_at"] = last_run["completed_at"].isoformat()

        return jsonify({
            "total_resources":    total_resources,
            "resources_by_type":  resources_by_type,
            "total_alerts":       total_alerts,
            "alerts_by_severity": alerts_by_severity,
            "total_cost_usd":     round(total_cost, 2),
            "last_run":           last_run,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500