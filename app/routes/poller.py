from datetime import datetime

from flask import Blueprint, jsonify, render_template
from psycopg2.extras import RealDictCursor
from db.connection import get_connection

poller_bp = Blueprint("poller", __name__)


@poller_bp.route("/poller")
def poller_page():
    return render_template("poller.html", active_page="poller")


@poller_bp.route("/api/poller")
def get_poller_status():
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, status, started_at, completed_at,
                       resources_found, resources_new, resources_updated,
                       resources_deleted, alerts_triggered, alerts_resolved,
                       error_log,
                       EXTRACT(EPOCH FROM (completed_at - started_at))
                           AS duration_seconds
                FROM poller_runs
                ORDER BY started_at DESC LIMIT 20
            """
            )
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


@poller_bp.route("/api/poller/<int:run_id>/resource-map")
def get_poller_run_resource_map(run_id):
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, status, started_at, completed_at,
                       resources_found, resources_new, resources_updated,
                       resources_deleted, alerts_triggered
                FROM poller_runs
                WHERE id = %s
            """,
                (run_id,),
            )
            run_row = cur.fetchone()
            if not run_row:
                return jsonify({"error": "Run not found"}), 404

            run = dict(run_row)
            run_start = run["started_at"]
            run_end = run.get("completed_at") or datetime.utcnow()

            cur.execute(
                """
                SELECT id, started_at, completed_at
                FROM poller_runs
                WHERE started_at < %s
                ORDER BY started_at DESC
                LIMIT 1
            """,
                (run_start,),
            )
            previous_run = cur.fetchone()

            cur.execute(
                """
                SELECT resource_id, resource_type, resource_name, region, state,
                       account_id, first_seen, last_seen, last_modified, deleted_at
                FROM resources
                WHERE first_seen >= %s
                  AND first_seen <= %s
                ORDER BY resource_type, COALESCE(resource_name, resource_id)
                LIMIT 300
            """,
                (run_start, run_end),
            )
            created = [_serialize_resource_row(dict(r)) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT resource_id, resource_type, resource_name, region, state,
                       account_id, first_seen, last_seen, last_modified, deleted_at
                FROM resources
                WHERE deleted_at IS NOT NULL
                  AND deleted_at >= %s
                  AND deleted_at <= %s
                ORDER BY resource_type, COALESCE(resource_name, resource_id)
                LIMIT 300
            """,
                (run_start, run_end),
            )
            deleted = [_serialize_resource_row(dict(r)) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT resource_id, resource_type, resource_name, region, state,
                       account_id, first_seen, last_seen, last_modified, deleted_at
                FROM resources
                WHERE is_active = TRUE
                  AND first_seen < %s
                  AND last_seen >= %s
                  AND last_seen <= %s
                ORDER BY resource_type, COALESCE(resource_name, resource_id)
                LIMIT 600
            """,
                (run_start, run_start, run_end),
            )
            existing = [_serialize_resource_row(dict(r)) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT resource_id, resource_type, resource_name, region, state,
                       account_id, first_seen, last_seen, last_modified, deleted_at
                FROM resources
                WHERE is_active = TRUE
                  AND first_seen < %s
                  AND last_seen >= %s
                  AND last_seen <= %s
                  AND last_modified IS NOT NULL
                  AND last_modified >= %s
                  AND last_modified <= %s
                ORDER BY resource_type, COALESCE(resource_name, resource_id)
                LIMIT 300
            """,
                (run_start, run_start, run_end, run_start, run_end),
            )
            updated = [_serialize_resource_row(dict(r)) for r in cur.fetchall()]

        response = {
            "run": _serialize_run_row(run),
            "previous_run": _serialize_run_row(dict(previous_run)) if previous_run else None,
            "categories": {
                "created": {"total": len(created), "by_type": _group_by_type(created), "items": created},
                "updated": {"total": len(updated), "by_type": _group_by_type(updated), "items": updated},
                "deleted": {"total": len(deleted), "by_type": _group_by_type(deleted), "items": deleted},
                "existing": {"total": len(existing), "by_type": _group_by_type(existing), "items": existing},
            },
        }
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _serialize_run_row(row: dict) -> dict:
    serialized = dict(row)
    for f in ["started_at", "completed_at"]:
        if serialized.get(f):
            serialized[f] = serialized[f].isoformat()
    return serialized


def _serialize_resource_row(row: dict) -> dict:
    serialized = dict(row)
    for f in ["first_seen", "last_seen", "last_modified", "deleted_at"]:
        if serialized.get(f):
            serialized[f] = serialized[f].isoformat()
    return serialized


def _group_by_type(items: list) -> list:
    grouped = {}
    for item in items:
        resource_type = item.get("resource_type") or "unknown"
        grouped[resource_type] = grouped.get(resource_type, 0) + 1
    return [
        {"resource_type": resource_type, "count": count}
        for resource_type, count in sorted(
            grouped.items(), key=lambda entry: (-entry[1], entry[0])
        )
    ]
