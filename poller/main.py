"""
AWS Resource Lifecycle Tracker — Poller
Phase 3: EC2 + EBS collectors active. Full poll cycle with DB lock,
run tracking, soft delete, and partial failure handling.
"""

import os
import signal
import sys
import time

import boto3

from collectors.ec2 import EC2Collector
from collectors.ebs_volumes import EBSVolumeCollector
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
from utils.logger import get_logger

logger = get_logger("poller.main")

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    logger.info(f"Received signal {signum} — shutting down gracefully")
    _shutdown = True


def _get_aws_session():
    """
    Create a boto3 session using the configured region.
    On EC2: credentials come from IAM Role automatically.
    Locally: credentials come from ~/.aws or environment variables.
    """
    region = os.environ.get("AWS_REGION", "ap-south-1")
    return boto3.Session(region_name=region)


def _get_account_id(session) -> str:
    """
    Get the AWS account ID via STS.
    Confirms AWS connectivity before the poll starts.
    """
    sts      = session.client("sts")
    identity = sts.get_caller_identity()
    return identity["Account"]


def _get_poll_interval() -> int:
    """Poll interval in seconds. Defaults to 60 minutes."""
    minutes = int(os.environ.get("POLL_INTERVAL_MINUTES", 60))
    return minutes * 60


def _get_collectors(session, account_id: str, region: str) -> list:
    """
    Return the list of collector instances to run each poll cycle.
    Phase 3: EC2 + EBS only.
    Phase 4: all remaining collectors added here.
    """
    return [
        EC2Collector(session, account_id, region),
        EBSVolumeCollector(session, account_id, region),
    ]


def _run_collector(collector, conn) -> dict:
    """
    Run one collector through the full cycle:
    collect -> upsert -> snapshot -> soft delete.

    Returns counts dict. Never raises — exceptions are caught and
    returned in counts['errors'] so other collectors still run.
    """
    counts = {
        "found":   0,
        "new":     0,
        "updated": 0,
        "deleted": 0,
        "errors":  [],
    }

    resource_type = collector.RESOURCE_TYPE

    try:
        # Get what DB currently thinks is active BEFORE calling AWS
        # so we can detect disappearances after the API call
        db_active_ids = get_active_resource_ids(conn, resource_type)

        resources = collector.collect()
        counts["found"] = len(resources)

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

        # Soft delete resources in DB but missing from AWS response
        disappeared_ids = db_active_ids - aws_returned_ids
        if disappeared_ids:
            logger.info(
                f"{len(disappeared_ids)} {resource_type} resource(s) "
                f"no longer in AWS — soft deleting"
            )
            deleted = soft_delete_resources(
                conn, resource_type, list(disappeared_ids)
            )
            counts["deleted"] = deleted

    except Exception as e:
        error_msg = f"[{resource_type}] {type(e).__name__}: {e}"
        logger.error(f"Collector failed: {error_msg}", exc_info=True)
        counts["errors"].append(error_msg)

    return counts


def run_poll_cycle(session, account_id: str, region: str) -> None:
    """
    Execute one complete poll cycle.
    """
    conn   = get_connection()
    run_id = None

    try:
        if not acquire_poll_lock(conn):
            release_connection(conn)
            return

        run_id = insert_poller_run(conn)
        logger.info(f"Poll cycle started — run_id={run_id}")

        total_found   = 0
        total_new     = 0
        total_updated = 0
        total_deleted = 0
        all_errors    = []

        collectors = _get_collectors(session, account_id, region)

        for collector in collectors:
            logger.info(f"Running collector: {collector.RESOURCE_TYPE}")
            counts = _run_collector(collector, conn)

            total_found   += counts["found"]
            total_new     += counts["new"]
            total_updated += counts["updated"]
            total_deleted += counts["deleted"]
            all_errors    += counts["errors"]

        if len(all_errors) == 0:
            status = "success"
        elif len(all_errors) < len(collectors):
            status = "partial_failure"
        else:
            status = "failed"

        error_log = "\n".join(all_errors) if all_errors else None

        update_poller_run(
            conn,
            run_id=run_id,
            status=status,
            resources_found=total_found,
            resources_new=total_new,
            resources_updated=total_updated,
            resources_deleted=total_deleted,
            error_log=error_log,
        )

        logger.info(
            f"Poll cycle complete — run_id={run_id} status={status} "
            f"found={total_found} new={total_new} "
            f"updated={total_updated} deleted={total_deleted}"
        )

        if all_errors:
            logger.warning(
                "Collector errors this cycle:\n" + "\n".join(all_errors)
            )

    except Exception as e:
        logger.error(f"Unexpected error in poll cycle: {e}", exc_info=True)
        if run_id is not None:
            try:
                update_poller_run(
                    conn,
                    run_id=run_id,
                    status="failed",
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
        logger.error(
            f"Could not establish AWS session: {e}. "
            f"On EC2: check IAM Role is attached. "
            f"Locally: check ~/.aws credentials or environment variables."
        )
        sys.exit(1)

    poll_interval = _get_poll_interval()
    logger.info(f"Poll interval: {poll_interval // 60} minutes")
    logger.info(
        f"Active collectors: "
        f"{[c.RESOURCE_TYPE for c in _get_collectors(session, account_id, region)]}"
    )

    while not _shutdown:
        try:
            run_poll_cycle(session, account_id, region)
        except Exception as e:
            logger.error(
                f"Unexpected error outside poll cycle: {e}", exc_info=True
            )

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