from flask import Blueprint, jsonify, render_template, request
from psycopg2.extras import RealDictCursor
from db.connection import get_connection

resources_bp = Blueprint("resources", __name__)


@resources_bp.route("/resources")
def resources_page():
    return render_template("resources.html", active_page="resources")


@resources_bp.route("/resources/<resource_type>/<path:resource_id>")
def resource_detail_page(resource_type, resource_id):
    return render_template("resource_detail.html", active_page="resources")


@resources_bp.route("/api/resources")
def list_resources():
    try:
        conn      = get_connection()
        page_size = int(request.args.get("page_size", 100))
        page      = max(1, int(request.args.get("page", 1)))
        offset    = (page - 1) * page_size

        filter_type   = request.args.get("type")
        filter_state  = request.args.get("state")
        filter_region = request.args.get("region")

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

        where = " AND ".join(conditions)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"SELECT COUNT(*) as total FROM resources WHERE {where}",
                params
            )
            total = cur.fetchone()["total"]

            cur.execute(
                f"""SELECT resource_id, resource_type, resource_name,
                           account_id, region, state, created_at, first_seen,
                           last_seen, last_modified, tags, estimated_cost_usd,
                           is_active, deleted_at
                    FROM resources WHERE {where}
                    ORDER BY first_seen DESC LIMIT %s OFFSET %s""",
                params + [page_size, offset],
            )
            rows = [_serialize(dict(r)) for r in cur.fetchall()]

        return jsonify({
            "resources": rows,
            "total":     total,
            "page":      page,
            "page_size": page_size,
            "pages":     max(1, (total + page_size - 1) // page_size),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@resources_bp.route("/api/resources/<resource_type>/<path:resource_id>")
def get_resource(resource_type, resource_id):
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute("""
                SELECT * FROM resources
                WHERE resource_id = %s AND resource_type = %s
            """, (resource_id, resource_type))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Resource not found"}), 404
            resource = _serialize(dict(row))

            cur.execute("""
                SELECT id, polled_at, state, tags, estimated_cost_usd
                FROM resource_snapshots
                WHERE resource_id = %s AND resource_type = %s
                ORDER BY polled_at ASC
            """, (resource_id, resource_type))
            snapshots = []
            for s in cur.fetchall():
                d = dict(s)
                if d.get("polled_at"):
                    d["polled_at"] = d["polled_at"].isoformat()
                if d.get("estimated_cost_usd"):
                    d["estimated_cost_usd"] = float(d["estimated_cost_usd"])
                snapshots.append(d)

            cur.execute("""
                SELECT id, alert_type, severity, message,
                       triggered_at, resolved_at, acknowledged
                FROM alerts
                WHERE resource_id = %s AND resource_type = %s
                ORDER BY triggered_at DESC
            """, (resource_id, resource_type))
            alerts = []
            for a in cur.fetchall():
                d = dict(a)
                if d.get("triggered_at"):
                    d["triggered_at"] = d["triggered_at"].isoformat()
                if d.get("resolved_at"):
                    d["resolved_at"] = d["resolved_at"].isoformat()
                alerts.append(d)

        return jsonify({
            "resource":  resource,
            "snapshots": snapshots,
            "alerts":    alerts,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _serialize(r):
    for f in ["created_at", "first_seen", "last_seen", "last_modified", "deleted_at"]:
        if r.get(f):
            r[f] = r[f].isoformat()
    if r.get("estimated_cost_usd"):
        r["estimated_cost_usd"] = float(r["estimated_cost_usd"])
    return r