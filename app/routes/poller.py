"""
Poller status route.

GET /api/poller
    Returns last 20 poller runs with status, counts, and error logs.
"""

from flask import Blueprint, jsonify
from psycopg2.extras import RealDictCursor

from app.db.connection import get_connection

poller_bp = Blueprint("poller", __name__)


@poller_bp.route("/api/poller")
def get_poller_status():
    """Last 20 poller runs — status, counts, duration, errors."""
    try:
        conn = get_connection()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    id, status, started_at, completed_at,
                    resources_found, resources_new, resources_updated,
                    resources_deleted, alerts_triggered, alerts_resolved,
                    error_log,
                    EXTRACT(EPOCH FROM (completed_at - started_at))
                        AS duration_seconds
                FROM poller_runs
                ORDER BY started_at DESC
                LIMIT 20
            """)

            runs = []
            for row in cur.fetchall():
                r = dict(row)
                if r.get("started_at"):
                    r["started_at"] = r["started_at"].isoformat()
                if r.get("completed_at"):
                    r["completed_at"] = r["completed_at"].isoformat()
                if r.get("duration_seconds"):
                    r["duration_seconds"] = round(float(r["duration_seconds"]), 1)
                runs.append(r)

        return jsonify({"runs": runs, "total": len(runs)})

    except Exception as e:
        return jsonify({"error": str(e)}), 500