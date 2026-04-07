from flask import Blueprint, jsonify, render_template, request
from psycopg2.extras import RealDictCursor
from db.connection import get_connection

alerts_bp = Blueprint("alerts", __name__)
PAGE_SIZE = 100


@alerts_bp.route("/alerts")
def alerts_page():
    return render_template("alerts.html", active_page="alerts")


@alerts_bp.route("/api/alerts")
def list_alerts():
    try:
        conn = get_connection()

        filter_severity = request.args.get("severity")
        filter_type     = request.args.get("type")
        filter_status   = request.args.get("status", "active")
        page            = max(1, int(request.args.get("page", 1)))
        offset          = (page - 1) * PAGE_SIZE

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Parameterized query with NULL-check pattern - no dynamic SQL construction
            cur.execute("""
                SELECT COUNT(*) as total FROM alerts a
                WHERE (%s IS NULL OR a.severity = %s)
                  AND (%s IS NULL OR a.alert_type = %s)
                  AND (CASE %s
                       WHEN 'active' THEN a.resolved_at IS NULL
                       WHEN 'resolved' THEN a.resolved_at IS NOT NULL
                       ELSE TRUE END)
            """, [
                filter_severity, filter_severity,
                filter_type, filter_type,
                filter_status
            ])
            total = cur.fetchone()["total"]

            cur.execute("""
                SELECT a.id, a.resource_id, a.resource_type,
                       a.alert_type, a.severity, a.message,
                       a.triggered_at, a.resolved_at, a.acknowledged,
                       r.resource_name, r.region
                FROM alerts a
                LEFT JOIN resources r
                    ON  a.resource_id   = r.resource_id
                    AND a.resource_type = r.resource_type
                WHERE (%s IS NULL OR a.severity = %s)
                  AND (%s IS NULL OR a.alert_type = %s)
                  AND (CASE %s
                       WHEN 'active' THEN a.resolved_at IS NULL
                       WHEN 'resolved' THEN a.resolved_at IS NOT NULL
                       ELSE TRUE END)
                ORDER BY a.triggered_at DESC
                LIMIT %s OFFSET %s
            """, [
                filter_severity, filter_severity,
                filter_type, filter_type,
                filter_status,
                PAGE_SIZE, offset
            ])
            rows = []
            for row in cur.fetchall():
                d = dict(row)
                if d.get("triggered_at"):
                    d["triggered_at"] = d["triggered_at"].isoformat()
                if d.get("resolved_at"):
                    d["resolved_at"] = d["resolved_at"].isoformat()
                rows.append(d)

        return jsonify({
            "alerts":    rows,
            "total":     total,
            "page":      page,
            "page_size": PAGE_SIZE,
            "pages":     max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@alerts_bp.route("/api/alerts/<int:alert_id>/acknowledge", methods=["POST"])
def acknowledge_alert(alert_id):
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE alerts SET acknowledged = TRUE
                WHERE id = %s AND acknowledged = FALSE
            """, (alert_id,))
            updated = cur.rowcount
            conn.commit()

        if updated == 0:
            return jsonify({
                "success": False,
                "error": "Not found or already acknowledged"
            }), 404
        return jsonify({"success": True, "alert_id": alert_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500