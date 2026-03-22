"""
Database cleanup jobs — data retention enforcement.

Runs after every successful poll cycle.
All queries are idempotent — running when nothing needs cleaning
is instant and harmless.

Retention policy:
  resource_snapshots  → full granularity for 7 days
                        1 row per resource per day for 7-90 days
                        deleted after 90 days
  raw_api_response    → nulled out after 48 hours (storage saving)
  alerts              → deleted after 1 year
  poller_runs         → deleted after 90 days
"""

from db.connection import get_connection, release_connection
from utils.logger import get_logger

logger = get_logger("poller.utils.cleanup")


def run_cleanup() -> None:
    """
    Run all cleanup jobs.
    Called after every successful poll cycle in main.py.
    Errors are logged but never raised — cleanup failure
    must never affect the poll cycle result.
    """
    conn = get_connection()
    try:
        _cleanup_raw_api_responses(conn)
        _cleanup_old_snapshots(conn)
        _cleanup_old_alerts(conn)
        _cleanup_old_poller_runs(conn)
        logger.info("Cleanup jobs completed")
    except Exception as e:
        logger.error(f"Cleanup job error: {e}", exc_info=True)
    finally:
        release_connection(conn)


def _cleanup_raw_api_responses(conn) -> None:
    """
    Null out raw_api_response older than 48 hours.
    The structured columns are preserved — only the raw JSON blob is cleared.
    This prevents the resource_snapshots table from growing too large.
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE resource_snapshots
            SET raw_api_response = NULL
            WHERE polled_at < NOW() - INTERVAL '48 hours'
              AND raw_api_response IS NOT NULL
        """)
        count = cur.rowcount
        conn.commit()
    if count > 0:
        logger.info(f"Nulled raw_api_response on {count} snapshot row(s) older than 48h")


def _cleanup_old_snapshots(conn) -> None:
    """
    Enforce snapshot retention policy:
      - Keep all snapshots from the last 7 days (full granularity)
      - For 7-90 days old: keep only the earliest snapshot per resource per day
      - Delete everything older than 90 days
    """
    with conn.cursor() as cur:

        # Step 1: Delete snapshots older than 90 days entirely
        cur.execute("""
            DELETE FROM resource_snapshots
            WHERE polled_at < NOW() - INTERVAL '90 days'
        """)
        deleted_old = cur.rowcount

        # Step 2: For 7-90 days range, keep only 1 row per resource per day
        cur.execute("""
            DELETE FROM resource_snapshots
            WHERE polled_at < NOW() - INTERVAL '7 days'
              AND polled_at >= NOW() - INTERVAL '90 days'
              AND id NOT IN (
                  SELECT DISTINCT ON (
                      resource_id,
                      resource_type,
                      DATE(polled_at)
                  ) id
                  FROM resource_snapshots
                  WHERE polled_at < NOW() - INTERVAL '7 days'
                    AND polled_at >= NOW() - INTERVAL '90 days'
                  ORDER BY
                      resource_id,
                      resource_type,
                      DATE(polled_at),
                      polled_at ASC
              )
        """)
        deleted_thinned = cur.rowcount
        conn.commit()

    total = deleted_old + deleted_thinned
    if total > 0:
        logger.info(
            f"Snapshot cleanup: deleted {deleted_old} rows > 90 days, "
            f"thinned {deleted_thinned} rows in 7-90 day range"
        )


def _cleanup_old_alerts(conn) -> None:
    """Delete alerts older than 1 year."""
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM alerts
            WHERE triggered_at < NOW() - INTERVAL '1 year'
        """)
        count = cur.rowcount
        conn.commit()
    if count > 0:
        logger.info(f"Deleted {count} alert(s) older than 1 year")


def _cleanup_old_poller_runs(conn) -> None:
    """Delete poller_run records older than 90 days."""
    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM poller_runs
            WHERE started_at < NOW() - INTERVAL '90 days'
        """)
        count = cur.rowcount
        conn.commit()
    if count > 0:
        logger.info(f"Deleted {count} poller_run record(s) older than 90 days")