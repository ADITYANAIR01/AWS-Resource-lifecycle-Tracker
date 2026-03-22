"""
Resources routes.

GET /api/resources
    Returns paginated, filterable list of active resources.
    Query params: type, state, region, page (default 1)

GET /api/resources/<resource_type>/<path:resource_id>
    Returns full detail for one resource:
      - Resource metadata
      - Full snapshot timeline
      - All alerts for this resource
"""

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from db.connection import get_connection

resources_bp = Blueprint("resources", __name__)

PAGE_SIZE = 100


@resources_bp.route("/api/resources")
def list_resources():
    """
    Filterable, paginated resource list.
    All filters are optional — returns all active resources if none provided.
    """
    try:
        conn = get_connection()

        # Read optional filter params
        filter_type   = request.args.get("type")
        filter_state  = request.args.get("state")
        filter_region = request.args.get("region")
        page          = max(1, int(request.args.get("page", 1)))
        offset        = (page - 1) * PAGE_SIZE

        # Build parameterized query dynamically
        conditions = ["is_active = TRUE"]
        params     = []

        if filter_type:
            conditions.append("resource_type = %s")
            params.append(filter_type)

        if filter_state:
            conditions.append("state = %s")
            params.append(filter_state)

        if filter_region:
            conditions.append("region = %s")
            params.append(filter_region)

        where_clause = " AND ".join(conditions)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            # Count total matching rows for pagination
            cur.execute(
                f"SELECT COUNT(*) as total FROM resources WHERE {where_clause}",
                params,
            )
            total = cur.fetchone()["total"]

            # Fetch page of results
            cur.execute(
                f"""
                SELECT
                    resource_id, resource_type, resource_name,
                    account_id, region, state,
                    created_at, first_seen, last_seen, last_modified,
                    tags, estimated_cost_usd, is_active, deleted_at
                FROM resources
                WHERE {where_clause}
                ORDER BY first_seen DESC
                LIMIT %s OFFSET %s
                """,
                params + [PAGE_SIZE, offset],
            )
            rows = [_serialize_resource(dict(r)) for r in cur.fetchall()]

        return jsonify({
            "resources": rows,
            "total":     total,
            "page":      page,
            "page_size": PAGE_SIZE,
            "pages":     max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@resources_bp.route("/api/resources/<resource_type>/<path:resource_id>")
def get_resource(resource_type, resource_id):
    """
    Full detail for one resource — metadata + timeline + alerts.
    """
    try:
        conn = get_connection()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            # Resource metadata
            cur.execute("""
                SELECT *
                FROM resources
                WHERE resource_id   = %s
                  AND resource_type = %s
            """, (resource_id, resource_type))

            row = cur.fetchone()
            if row is None:
                return jsonify({"error": "Resource not found"}), 404

            resource = _serialize_resource(dict(row))

            # Snapshot timeline — oldest first
            cur.execute("""
                SELECT
                    id, polled_at, state, tags,
                    estimated_cost_usd
                FROM resource_snapshots
                WHERE resource_id   = %s
                  AND resource_type = %s
                ORDER BY polled_at ASC
            """, (resource_id, resource_type))

            snapshots = []
            for snap in cur.fetchall():
                s = dict(snap)
                if s.get("polled_at"):
                    s["polled_at"] = s["polled_at"].isoformat()
                snapshots.append(s)

            # All alerts for this resource
            cur.execute("""
                SELECT
                    id, alert_type, severity, message,
                    triggered_at, resolved_at, acknowledged
                FROM alerts
                WHERE resource_id   = %s
                  AND resource_type = %s
                ORDER BY triggered_at DESC
            """, (resource_id, resource_type))

            alerts = []
            for alert in cur.fetchall():
                a = dict(alert)
                if a.get("triggered_at"):
                    a["triggered_at"] = a["triggered_at"].isoformat()
                if a.get("resolved_at"):
                    a["resolved_at"] = a["resolved_at"].isoformat()
                alerts.append(a)

        return jsonify({
            "resource":  resource,
            "snapshots": snapshots,
            "alerts":    alerts,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _serialize_resource(resource: dict) -> dict:
    """Convert datetime fields to ISO strings for JSON serialization."""
    for field in ["created_at", "first_seen", "last_seen",
                  "last_modified", "deleted_at"]:
        if resource.get(field):
            resource[field] = resource[field].isoformat()
    if resource.get("estimated_cost_usd"):
        resource["estimated_cost_usd"] = float(resource["estimated_cost_usd"])
    return resource