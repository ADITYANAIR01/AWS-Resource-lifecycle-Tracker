"""
All database read/write operations for the poller.

Rules enforced here:
  - No SQL lives anywhere else in the codebase
  - Every query uses parameterized placeholders (%s) — never string formatting
  - Every function takes a connection as its first argument
  - Callers get/release connections from the pool
  - JSONB columns always use psycopg2.extras.Json wrapper
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import psycopg2
from psycopg2.extras import Json

from utils.logger import get_logger

logger = get_logger("poller.db.queries")


# =============================================================================
# Helpers
# =============================================================================

def _make_serializable(obj):
    """
    Recursively convert a boto3 API response dict to JSON-serializable types.
    boto3 returns datetime objects and Decimal values which psycopg2 Json
    cannot serialize without this conversion.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(i) for i in obj]
    return obj


# =============================================================================
# Poll Lock
# =============================================================================

def acquire_poll_lock(conn) -> bool:
    """
    Check if a poll cycle is already running.

    Returns True if safe to proceed.
    Returns False if another poll is actively running (started < 30 min ago).

    If a stale 'running' record exists (>= 30 min old), mark it failed
    and proceed — the previous process likely crashed.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, started_at
            FROM poller_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()

        if row is None:
            return True

        run_id, started_at = row

        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_minutes = (now - started_at).total_seconds() / 60

        if age_minutes < 30:
            logger.warning(
                f"Poll cycle already running (run_id={run_id}, "
                f"started {age_minutes:.1f} min ago) — skipping this cycle"
            )
            return False

        logger.warning(
            f"Stale poll lock found (run_id={run_id}, "
            f"started {age_minutes:.1f} min ago) — marking as failed and proceeding"
        )
        cur.execute("""
            UPDATE poller_runs
            SET status       = 'failed',
                completed_at = NOW(),
                error_log    = 'Marked failed by lock cleanup — process likely crashed'
            WHERE id = %s
        """, (run_id,))
        conn.commit()
        return True


# =============================================================================
# Poller Run Tracking
# =============================================================================

def insert_poller_run(conn) -> int:
    """
    Insert a new poller_run row with status 'running'.
    Returns the new run ID.
    """
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO poller_runs (status, started_at)
            VALUES ('running', NOW())
            RETURNING id
        """)
        run_id = cur.fetchone()[0]
        conn.commit()
        logger.debug(f"Poller run started — run_id={run_id}")
        return run_id


def update_poller_run(
    conn,
    run_id: int,
    status: str,
    resources_found: int = 0,
    resources_new: int = 0,
    resources_updated: int = 0,
    resources_deleted: int = 0,
    alerts_triggered: int = 0,
    alerts_resolved: int = 0,
    error_log: Optional[str] = None,
) -> None:
    """
    Update a poller_run record at the end of a poll cycle.
    status must be: 'success', 'partial_failure', or 'failed'
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE poller_runs SET
                status            = %s,
                completed_at      = NOW(),
                resources_found   = %s,
                resources_new     = %s,
                resources_updated = %s,
                resources_deleted = %s,
                alerts_triggered  = %s,
                alerts_resolved   = %s,
                error_log         = %s
            WHERE id = %s
        """, (
            status,
            resources_found,
            resources_new,
            resources_updated,
            resources_deleted,
            alerts_triggered,
            alerts_resolved,
            error_log,
            run_id,
        ))
        conn.commit()
        logger.debug(f"Poller run updated — run_id={run_id} status={status}")


# =============================================================================
# Resource Upsert
# =============================================================================

def insert_or_update_resource(conn, resource: dict) -> str:
    """
    Upsert a resource into the resources table.

    INSERT if new. UPDATE if exists.
    last_modified only changes when state changes — not on every poll.

    Returns 'inserted' or 'updated'.
    """
    tags_json = Json(resource.get("tags") or {})

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO resources (
                resource_id,
                resource_type,
                resource_name,
                account_id,
                region,
                state,
                created_at,
                first_seen,
                last_seen,
                last_modified,
                tags,
                estimated_cost_usd,
                is_active
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                NOW(), NOW(), NOW(),
                %s, %s, TRUE
            )
            ON CONFLICT (resource_id, resource_type) DO UPDATE SET
                resource_name      = EXCLUDED.resource_name,
                state              = EXCLUDED.state,
                last_seen          = NOW(),
                last_modified      = CASE
                    WHEN resources.state IS DISTINCT FROM EXCLUDED.state
                    THEN NOW()
                    ELSE resources.last_modified
                END,
                tags               = EXCLUDED.tags,
                estimated_cost_usd = EXCLUDED.estimated_cost_usd,
                is_active          = TRUE,
                deleted_at         = NULL
            RETURNING (xmax = 0) AS was_inserted
        """, (
            resource["resource_id"],
            resource["resource_type"],
            resource.get("resource_name"),
            resource["account_id"],
            resource["region"],
            resource.get("state"),
            resource.get("created_at"),
            tags_json,
            resource.get("estimated_cost_usd", Decimal("0")),
        ))

        was_inserted = cur.fetchone()[0]
        conn.commit()
        return "inserted" if was_inserted else "updated"


# =============================================================================
# Snapshot History
# =============================================================================

def insert_resource_snapshot(conn, resource: dict) -> None:
    """
    Insert one snapshot row per resource per poll cycle.
    Builds the lifecycle timeline shown on the resource detail page.
    raw_api_response is nulled out after 48 hours by the cleanup job.
    """
    tags_json = Json(resource.get("tags") or {})
    raw_json  = Json(_make_serializable(resource.get("raw_api_response") or {}))

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO resource_snapshots (
                resource_id,
                resource_type,
                polled_at,
                state,
                tags,
                estimated_cost_usd,
                raw_api_response
            ) VALUES (
                %s, %s, NOW(), %s, %s, %s, %s
            )
        """, (
            resource["resource_id"],
            resource["resource_type"],
            resource.get("state"),
            tags_json,
            resource.get("estimated_cost_usd", Decimal("0")),
            raw_json,
        ))
        conn.commit()


# =============================================================================
# Soft Delete
# =============================================================================

def get_active_resource_ids(conn, resource_type: str) -> set:
    """
    Return the set of resource_ids currently marked active in the DB
    for a given resource_type.
    Used to detect resources missing from the latest AWS API response.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT resource_id
            FROM resources
            WHERE resource_type = %s
              AND is_active = TRUE
        """, (resource_type,))
        rows = cur.fetchall()
        return {row[0] for row in rows}


def soft_delete_resources(conn, resource_type: str, resource_ids: list) -> int:
    """
    Mark resources as inactive.
    Called when resources are in the DB but not returned by AWS API.
    Returns count of rows updated.
    """
    if not resource_ids:
        return 0

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE resources
            SET is_active  = FALSE,
                deleted_at = NOW()
            WHERE resource_type = %s
              AND resource_id   = ANY(%s)
              AND is_active     = TRUE
        """, (resource_type, list(resource_ids)))

        count = cur.rowcount
        conn.commit()

        if count > 0:
            logger.info(
                f"Soft deleted {count} {resource_type} resource(s) "
                f"no longer present in AWS"
            )
        return count