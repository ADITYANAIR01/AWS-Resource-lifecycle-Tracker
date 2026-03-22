"""
Alert evaluator.

Runs after every poll cycle:
1. Evaluates all alert rules against the resources table
2. Inserts new alerts (with deduplication)
3. Auto-resolves alerts whose conditions are no longer true
4. Sends SNS notifications for new unnotified alerts
5. Sends SNS resolution notifications for newly resolved alerts

Returns counts: alerts_triggered, alerts_resolved
"""

import os

from alerts.rules import ALERT_RULES, _required_tags
from db.queries import (
    get_open_alert,
    get_open_alerts_by_type,
    get_unnotified_alerts,
    get_unnotified_resolutions,
    insert_alert,
    mark_alert_notified,
    mark_resolution_notified,
    resolve_alert,
    run_alert_query,
)
from notifier.sns import send_alert, send_resolution
from utils.logger import get_logger

logger = get_logger("poller.alerts.evaluator")


def run_alert_evaluation(conn) -> dict:
    """
    Run the full alert evaluation cycle.

    Returns:
        {
            "triggered": int,  — new alerts inserted
            "resolved":  int,  — alerts auto-resolved
        }
    """
    triggered = 0
    resolved  = 0

    try:
        # Step 1 — Evaluate standard rules
        for rule in ALERT_RULES:
            t, r = _evaluate_rule(conn, rule)
            triggered += t
            resolved  += r

        # Step 2 — Evaluate tag rules (dynamic — one rule per required tag)
        t, r = _evaluate_tag_rules(conn)
        triggered += t
        resolved  += r

        # Step 3 — Send SNS for new unnotified alerts
        _send_new_alert_notifications(conn)

        # Step 4 — Send SNS for newly resolved alerts
        _send_resolution_notifications(conn)

        logger.info(
            f"Alert evaluation complete — "
            f"triggered={triggered} resolved={resolved}"
        )

    except Exception as e:
        logger.error(f"Alert evaluation failed: {e}", exc_info=True)

    return {"triggered": triggered, "resolved": resolved}


# ---------------------------------------------------------------------------
# Standard rule evaluation
# ---------------------------------------------------------------------------

def _evaluate_rule(conn, rule: dict) -> tuple:
    """
    Evaluate one alert rule.
    Returns (triggered_count, resolved_count).
    """
    alert_type = rule["type"]
    severity   = rule["severity"]
    triggered  = 0
    resolved   = 0

    try:
        # Get params for this rule's query
        params = rule["get_params"]()

        # Run the rule query to find matching resources
        matching_rows = run_alert_query(conn, rule["query"], params)

        # Build set of resource keys currently matching the rule
        matching_keys = {
            (row["resource_id"], row["resource_type"])
            for row in matching_rows
        }

        # Insert new alerts for resources not already alerted
        for row in matching_rows:
            resource_id   = row["resource_id"]
            resource_type = row["resource_type"]

            # Deduplication check — skip if open alert already exists
            existing = get_open_alert(conn, resource_id, resource_type, alert_type)
            if existing:
                continue

            message = rule["message_fn"](row)
            insert_alert(
                conn,
                resource_id=resource_id,
                resource_type=resource_type,
                alert_type=alert_type,
                severity=severity,
                message=message,
            )
            triggered += 1
            logger.info(
                f"Alert triggered — type={alert_type} "
                f"resource={row.get('resource_name', resource_id)} "
                f"severity={severity}"
            )

        # Auto-resolve: find open alerts for this rule that no longer match
        open_alerts = get_open_alerts_by_type(conn, alert_type)
        for alert in open_alerts:
            key = (alert["resource_id"], alert["resource_type"])
            if key not in matching_keys:
                resolve_alert(conn, alert["id"])
                resolved += 1
                logger.info(
                    f"Alert auto-resolved — type={alert_type} "
                    f"resource={alert['resource_id']}"
                )

    except Exception as e:
        logger.error(
            f"Rule evaluation failed for type={alert_type}: {e}",
            exc_info=True
        )

    return triggered, resolved


# ---------------------------------------------------------------------------
# Tag rule evaluation — dynamic per required tag key
# ---------------------------------------------------------------------------

def _evaluate_tag_rules(conn) -> tuple:
    """
    Evaluate tag compliance rules.
    Disabled by default — opt-in via ALERT_TAGS_ENABLED=true in .env.
    One rule per required tag key — all resource types except snapshots.
    Returns (triggered_count, resolved_count).
    """
    tags_enabled = os.environ.get("ALERT_TAGS_ENABLED", "false").lower() == "true"
    if not tags_enabled:
        return 0, 0

    triggered = 0
    resolved  = 0

    required_tags = _required_tags()


# ---------------------------------------------------------------------------
# SNS notification dispatch
# ---------------------------------------------------------------------------

def _send_new_alert_notifications(conn) -> None:
    """
    Send SNS emails for all alerts where notified=False.
    Marks each as notified after successful send.
    If SNS send fails, leave notified=False — will retry next cycle.
    """
    unnotified = get_unnotified_alerts(conn)

    for alert in unnotified:
        sent = send_alert(alert)
        if sent:
            mark_alert_notified(conn, alert["id"])


def _send_resolution_notifications(conn) -> None:
    """
    Send SNS resolution emails for alerts resolved this cycle.
    """
    resolutions = get_unnotified_resolutions(conn)

    for alert in resolutions:
        sent = send_resolution(alert)
        if sent:
            mark_resolution_notified(conn, alert["id"])