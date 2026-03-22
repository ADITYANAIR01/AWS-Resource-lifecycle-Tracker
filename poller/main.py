"""
AWS Resource Lifecycle Tracker — Poller
Phase 8: Full poll cycle with static snapshot export to S3.
"""

import os
import signal
import sys
import time

import boto3

from collectors.ec2 import EC2Collector
from collectors.ebs_volumes import EBSVolumeCollector
from collectors.ebs_snapshots import EBSSnapshotCollector
from collectors.rds_instances import RDSInstanceCollector
from collectors.rds_snapshots import RDSSnapshotCollector
from collectors.s3 import S3Collector
from collectors.elastic_ips import ElasticIPCollector
from collectors.security_groups import SecurityGroupCollector
from collectors.iam_users import IAMUserCollector
from collectors.cloudwatch_alarms import CloudWatchAlarmCollector
from alerts.evaluator import run_alert_evaluation
from db.connection import close_pool, get_connection, init_pool, release_connection
from db.queries import (
    acquire_poll_lock,
    get_active_resource_ids,
    insert_or_update_resource,
    insert_poller_run,
    insert_resource_snapshot,
    soft_delete_resources,
    update_poller_run,
)
from export.generator import generate_snapshot
from export.uploader import upload_snapshot
from notifier.sns import send_poller_failure
from utils.cleanup import run_cleanup
from utils.logger import get_logger

logger = get_logger("poller.main")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum} — shutting down gracefully")
    _shutdown = True


def _get_aws_session():
    region = os.environ.get("AWS_REGION", "ap-south-1")
    return boto3.Session(region_name=region)


def _get_account_id(session) -> str:
    return session.client("sts").get_caller_identity()["Account"]


def _get_poll_interval() -> int:
    return int(os.environ.get("POLL_INTERVAL_MINUTES", 60)) * 60


def _get_collectors(session, account_id: str, region: str) -> list:
    return [
        EC2Collector(session, account_id, region),
        EBSVolumeCollector(session, account_id, region),
        EBSSnapshotCollector(session, account_id, region),
        RDSInstanceCollector(session, account_id, region),
        RDSSnapshotCollector(session, account_id, region),
        S3Collector(session, account_id, region),
        ElasticIPCollector(session, account_id, region),
        SecurityGroupCollector(session, account_id, region),
        IAMUserCollector(session, account_id, region),
        CloudWatchAlarmCollector(session, account_id, region),
    ]


def _run_collector(collector, conn) -> dict:
    counts = {
        "found": 0, "new": 0, "updated": 0,
        "deleted": 0, "errors": [],
    }
    resource_type = collector.RESOURCE_TYPE

    try:
        db_active_ids    = get_active_resource_ids(conn, resource_type)
        resources        = collector.collect()
        counts["found"]  = len(resources)
        aws_returned_ids = set()

        for resource in resources:
            resource_id = resource["resource_id"]
            aws_returned_ids.add(resource_id)

            result = insert_or_update_resource(conn, resource)
            if result == "inserted":
                counts["new"] += 1
                logger.info(
                    f"New {resource_type}: "
                    f"{resource.get('resource_name', resource_id)}"
                )
            else:
                counts["updated"] += 1

            insert_resource_snapshot(conn, resource)

        disappeared_ids = db_active_ids - aws_returned_ids
        if disappeared_ids:
            counts["deleted"] = soft_delete_resources(
                conn, resource_type, list(disappeared_ids)
            )

    except Exception as e:
        error_msg = f"[{resource_type}] {type(e).__name__}: {e}"
        logger.error(f"Collector failed: {error_msg}", exc_info=True)
        counts["errors"].append(error_msg)

    return counts


def _run_export(conn) -> None:
    """
    Generate static HTML snapshot and upload to S3.
    Runs after every successful or partial poll cycle.
    Never raises — export failure must not affect the poll result.
    """
    bucket = os.environ.get("S3_SNAPSHOT_BUCKET", "")
    if not bucket:
        logger.debug("S3_SNAPSHOT_BUCKET not set — skipping snapshot export")
        return

    try:
        logger.info("Generating static snapshot")
        pages = generate_snapshot(conn)

        if not pages:
            logger.warning("Snapshot generation produced no pages — skipping upload")
            return

        # Build the data bundle for JSON export
        from export.generator import (
            _query_overview, _query_resources,
            _query_alerts, _query_poller,
        )
        snapshot_data = {
            "overview":  _query_overview(conn),
            "resources": _query_resources(conn),
            "alerts":    _query_alerts(conn),
            "poller":    _query_poller(conn),
        }

        success = upload_snapshot(pages, snapshot_data)
        if success:
            logger.info("Static snapshot export complete")
        else:
            logger.warning("Static snapshot export completed with errors")

    except Exception as e:
        logger.error(f"Snapshot export failed: {e}", exc_info=True)


def run_poll_cycle(session, account_id: str, region: str) -> None:
    conn   = get_connection()
    run_id = None

    try:
        if not acquire_poll_lock(conn):
            return

        run_id = insert_poller_run(conn)
        logger.info(f"Poll cycle started — run_id={run_id}")

        total_found   = 0
        total_new     = 0
        total_updated = 0
        total_deleted = 0
        all_errors    = []

        for collector in _get_collectors(session, account_id, region):
            logger.info(f"Running collector: {collector.RESOURCE_TYPE}")
            counts = _run_collector(collector, conn)
            total_found   += counts["found"]
            total_new     += counts["new"]
            total_updated += counts["updated"]
            total_deleted += counts["deleted"]
            all_errors    += counts["errors"]

        collectors_count = len(_get_collectors(session, account_id, region))
        if len(all_errors) == 0:
            status = "success"
        elif len(all_errors) < collectors_count:
            status = "partial_failure"
        else:
            status = "failed"

        error_log = "\n".join(all_errors) if all_errors else None

        # Alert evaluation
        alert_counts = {"triggered": 0, "resolved": 0}
        if status in ("success", "partial_failure"):
            alert_counts = run_alert_evaluation(conn)

        update_poller_run(
            conn,
            run_id=run_id,
            status=status,
            resources_found=total_found,
            resources_new=total_new,
            resources_updated=total_updated,
            resources_deleted=total_deleted,
            alerts_triggered=alert_counts["triggered"],
            alerts_resolved=alert_counts["resolved"],
            error_log=error_log,
        )

        logger.info(
            f"Poll cycle complete — run_id={run_id} status={status} "
            f"found={total_found} new={total_new} updated={total_updated} "
            f"deleted={total_deleted} alerts_triggered={alert_counts['triggered']} "
            f"alerts_resolved={alert_counts['resolved']}"
        )

        if all_errors:
            logger.warning("Collector errors:\n" + "\n".join(all_errors))
            send_poller_failure(status, "\n".join(all_errors))

        # Cleanup + snapshot export after successful or partial poll
        if status in ("success", "partial_failure"):
            run_cleanup()
            _run_export(conn)

    except Exception as e:
        logger.error(f"Unexpected error in poll cycle: {e}", exc_info=True)
        if run_id is not None:
            try:
                update_poller_run(
                    conn, run_id=run_id, status="failed",
                    error_log=f"Unexpected error: {type(e).__name__}: {e}",
                )
            except Exception:
                pass

    finally:
        release_connection(conn)


def main() -> None:
    logger.info("=" * 60)
    logger.info("AWS Resource Lifecycle Tracker — Poller starting")
    logger.info("=" * 60)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        init_pool()
    except Exception as e:
        logger.error(f"Fatal: could not initialise DB pool: {e}")
        sys.exit(1)

    try:
        session    = _get_aws_session()
        account_id = _get_account_id(session)
        region     = os.environ.get("AWS_REGION", "ap-south-1")
        logger.info(f"AWS session ready — account={account_id} region={region}")
    except Exception as e:
        logger.error(f"Could not establish AWS session: {e}")
        sys.exit(1)

    poll_interval = _get_poll_interval()
    bucket = os.environ.get("S3_SNAPSHOT_BUCKET", "not set")
    logger.info(f"Poll interval: {poll_interval // 60} minutes")
    logger.info(f"Snapshot bucket: {bucket}")

    while not _shutdown:
        try:
            run_poll_cycle(session, account_id, region)
        except Exception as e:
            logger.error(f"Unexpected error outside poll cycle: {e}", exc_info=True)

        logger.info(f"Sleeping {poll_interval // 60} minutes until next poll")

        for _ in range(poll_interval):
            if _shutdown:
                break
            time.sleep(1)

    logger.info("Poller shutting down")
    close_pool()
    logger.info("Poller stopped cleanly")


if __name__ == "__main__":
    main()