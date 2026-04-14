"""AWS Resource Lifecycle Tracker — Management CLI.

This CLI is intended for operational/admin actions (typically on the EC2 host)
that need direct access to the PostgreSQL database and AWS APIs.

It will automatically load environment variables from a local .env file
(if present) when variables are not already set in the process environment.

Usage examples:
  python manage.py poller run-now
  python manage.py alerts list --status active --limit 50
  python manage.py alerts acknowledge 123
  python manage.py alerts resolve 123
  python manage.py resources list --limit 50
  python manage.py snapshot generate
  python manage.py db cleanup
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional


# Ensure we can import poller modules (which use top-level imports like `db.*`)
_PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_ROOT / "poller"))

from utils.logger import get_logger  # noqa: E402


logger = get_logger("manage")


def _db():
    """Lazy DB imports.

    Keeps `python manage.py --help` working even if DB deps aren't installed.
    """
    try:
        from db.connection import (
            init_pool,
            close_pool,
            get_connection,
            release_connection,
        )

        return init_pool, close_pool, get_connection, release_connection
    except ModuleNotFoundError as e:
        raise SystemExit(
            "Database dependencies are not installed in this Python environment. "
            "Install poller requirements first (psycopg2-binary, boto3):\n\n"
            "  pip install -r poller\\requirements.txt\n"
        ) from e


def _queries():
    from db import queries as q

    return q


def _snapshot_modules():
    try:
        from export.generator import generate_snapshot, get_snapshot_data
        from export.uploader import upload_snapshot, get_snapshot_url

        return generate_snapshot, get_snapshot_data, upload_snapshot, get_snapshot_url
    except ModuleNotFoundError as e:
        raise SystemExit(
            "Snapshot dependencies are not installed in this Python environment. "
            "Install poller requirements first:\n\n"
            "  pip install -r poller\\requirements.txt\n"
        ) from e


def _cleanup_module():
    from utils.cleanup import run_cleanup

    return run_cleanup


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def _load_dotenv_if_present() -> None:
    """Best-effort .env loader (no external deps).

    Loads KEY=VALUE pairs from .env into os.environ *only if* the key is not
    already set.
    """
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception as e:
        logger.warning(f"Could not load .env: {e}")


def _require_env(*keys: str) -> None:
    missing = [k for k in keys if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            "Missing required env var(s): "
            + ", ".join(missing)
            + ". Set them in your shell or in a .env file."
        )


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _with_db_conn(fn):
    init_pool, close_pool, get_connection, release_connection = _db()

    init_pool()
    conn = None
    try:
        conn = get_connection()
        return fn(conn)
    finally:
        if conn is not None:
            release_connection(conn)
        close_pool()


def _import_poller_main():
    """Import poller/main.py as a module without name collisions."""
    poller_main_path = _PROJECT_ROOT / "poller" / "main.py"
    spec = importlib.util.spec_from_file_location("poller_main", poller_main_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load poller/main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -----------------------------------------------------------------------------
# Command handlers
# -----------------------------------------------------------------------------


def cmd_poller_run_now(_args: argparse.Namespace) -> int:
    _require_env("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")

    # poller.run_poll_cycle() uses the DB pool internally
    init_pool, close_pool, _get_connection, _release_connection = _db()

    init_pool()
    try:
        poller_main = _import_poller_main()

        import boto3

        region = os.environ.get("AWS_REGION", "ap-south-1")
        session = boto3.Session(region_name=region)
        account_id = session.client("sts").get_caller_identity()["Account"]

        logger.info(f"Triggering one poll cycle (account={account_id} region={region})")
        poller_main.run_poll_cycle(session, account_id, region)
        logger.info("Poll cycle finished")
        return 0
    finally:
        close_pool()


def cmd_alerts_list(args: argparse.Namespace) -> int:
    _require_env("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")

    def _run(conn):
        q = _queries()
        data = q.list_alerts(
            conn,
            status=args.status,
            severity=args.severity,
            alert_type=args.type,
            limit=args.limit,
            offset=args.offset,
        )
        _print_json(data)

    _with_db_conn(_run)
    return 0


def cmd_alerts_ack(args: argparse.Namespace) -> int:
    _require_env("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")

    def _run(conn):
        q = _queries()
        ok = q.acknowledge_alert(conn, args.id)
        if not ok:
            raise SystemExit(f"Alert not found or already acknowledged: id={args.id}")
        _print_json({"success": True, "alert_id": args.id, "acknowledged": True})

    _with_db_conn(_run)
    return 0


def cmd_alerts_resolve(args: argparse.Namespace) -> int:
    _require_env("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")

    def _run(conn):
        q = _queries()
        ok = q.resolve_alert_manual(conn, args.id)
        if not ok:
            raise SystemExit(f"Alert not found or already resolved: id={args.id}")
        _print_json({"success": True, "alert_id": args.id, "resolved": True})

    _with_db_conn(_run)
    return 0


def cmd_resources_list(args: argparse.Namespace) -> int:
    _require_env("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")

    def _run(conn):
        q = _queries()
        data = q.list_resources(
            conn,
            resource_type=args.type,
            state=args.state,
            region=args.region,
            limit=args.limit,
            offset=args.offset,
            active_only=not args.include_inactive,
        )
        _print_json(data)

    _with_db_conn(_run)
    return 0


def cmd_snapshot_generate(_args: argparse.Namespace) -> int:
    _require_env("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")

    # Snapshot upload requires bucket
    _require_env("S3_SNAPSHOT_BUCKET")

    def _run(conn):
        generate_snapshot, get_snapshot_data, upload_snapshot, get_snapshot_url = (
            _snapshot_modules()
        )

        logger.info("Generating static snapshot")
        pages = generate_snapshot(conn)
        if not pages:
            raise SystemExit("Snapshot generation produced no pages")

        snapshot_data = get_snapshot_data(conn)
        ok = upload_snapshot(pages, snapshot_data)
        if not ok:
            raise SystemExit("Snapshot upload completed with errors")

        presigned = get_snapshot_url()
        out = {"success": True}
        if presigned:
            out["presigned_url"] = presigned
        _print_json(out)

    _with_db_conn(_run)
    return 0


def cmd_db_cleanup(_args: argparse.Namespace) -> int:
    _require_env("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")

    # cleanup module manages its own DB connection; we just need the pool
    init_pool, close_pool, _get_connection, _release_connection = _db()
    run_cleanup = _cleanup_module()

    init_pool()
    try:
        run_cleanup()
        _print_json({"success": True})
        return 0
    finally:
        close_pool()


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="manage.py", add_help=True)
    sub = p.add_subparsers(dest="command", required=True)

    poller = sub.add_parser("poller", help="Poller operations")
    poller_sub = poller.add_subparsers(dest="poller_cmd", required=True)
    poller_run = poller_sub.add_parser("run-now", help="Trigger a single poll cycle")
    poller_run.set_defaults(func=cmd_poller_run_now)

    alerts = sub.add_parser("alerts", help="Alert operations")
    alerts_sub = alerts.add_subparsers(dest="alerts_cmd", required=True)

    alerts_list = alerts_sub.add_parser("list", help="List alerts")
    alerts_list.add_argument(
        "--status", choices=["active", "resolved", "all"], default="active"
    )
    alerts_list.add_argument(
        "--severity", choices=["critical", "warning", "info"], default=None
    )
    alerts_list.add_argument(
        "--type", dest="type", default=None, help="alert_type filter"
    )
    alerts_list.add_argument("--limit", type=int, default=50)
    alerts_list.add_argument("--offset", type=int, default=0)
    alerts_list.set_defaults(func=cmd_alerts_list)

    alerts_ack = alerts_sub.add_parser("acknowledge", help="Acknowledge an alert")
    alerts_ack.add_argument("id", type=int)
    alerts_ack.set_defaults(func=cmd_alerts_ack)

    alerts_resolve = alerts_sub.add_parser("resolve", help="Resolve an alert")
    alerts_resolve.add_argument("id", type=int)
    alerts_resolve.set_defaults(func=cmd_alerts_resolve)

    resources = sub.add_parser("resources", help="Resource operations")
    resources_sub = resources.add_subparsers(dest="resources_cmd", required=True)

    res_list = resources_sub.add_parser("list", help="List resources")
    res_list.add_argument(
        "--type", dest="type", default=None, help="resource_type filter"
    )
    res_list.add_argument("--state", default=None)
    res_list.add_argument("--region", default=None)
    res_list.add_argument("--include-inactive", action="store_true")
    res_list.add_argument("--limit", type=int, default=50)
    res_list.add_argument("--offset", type=int, default=0)
    res_list.set_defaults(func=cmd_resources_list)

    snapshot = sub.add_parser("snapshot", help="Snapshot operations")
    snapshot_sub = snapshot.add_subparsers(dest="snapshot_cmd", required=True)
    snap_gen = snapshot_sub.add_parser(
        "generate", help="Generate + upload static snapshot now"
    )
    snap_gen.set_defaults(func=cmd_snapshot_generate)

    db = sub.add_parser("db", help="Database operations")
    db_sub = db.add_subparsers(dest="db_cmd", required=True)
    db_cleanup = db_sub.add_parser("cleanup", help="Run retention/cleanup jobs")
    db_cleanup.set_defaults(func=cmd_db_cleanup)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    _load_dotenv_if_present()

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.func(args))
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
