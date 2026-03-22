"""
S3 snapshot uploader.

Uploads generated snapshot HTML pages to S3.

Structure:
  s3://bucket/latest/          ← always overwritten — most recent
  s3://bucket/archive/DATE/    ← archived per day — auto-deleted after 90 days
  s3://bucket/data/latest.json ← raw JSON data export
  s3://bucket/data/DATE.json   ← archived JSON per day

Never raises — upload failures are logged but never crash the poll cycle.
"""

import json
import os
from datetime import datetime, timezone

import boto3
from botocore.config import Config

from utils.logger import get_logger

logger = get_logger("poller.export.uploader")

_BOTO_CONFIG = Config(
    connect_timeout=15,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "adaptive"},
)


def _get_client():
    region = os.environ.get("AWS_REGION", "ap-south-1")
    return boto3.client("s3", region_name=region, config=_BOTO_CONFIG)


def _get_bucket() -> str:
    bucket = os.environ.get("S3_SNAPSHOT_BUCKET", "")
    if not bucket:
        logger.warning(
            "S3_SNAPSHOT_BUCKET not set — snapshot upload skipped. "
            "Set S3_SNAPSHOT_BUCKET in .env to enable."
        )
    return bucket


def upload_snapshot(pages: dict, snapshot_data: dict) -> bool:
    """
    Upload snapshot HTML pages and raw JSON data to S3.

    pages: dict of { 'index.html': html_string, ... }
    snapshot_data: dict of all data (for JSON export)

    Returns True if all uploads succeeded, False if any failed.
    """
    if not pages:
        logger.warning("No pages to upload — skipping")
        return False

    bucket = _get_bucket()
    if not bucket:
        return False

    client = _get_client()
    today  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    errors = []

    # Upload HTML pages
    for filename, html in pages.items():
        body = html.encode("utf-8")

        # latest/ — always overwrite
        latest_key = f"latest/{filename}"
        try:
            client.put_object(
                Bucket=bucket,
                Key=latest_key,
                Body=body,
                ContentType="text/html; charset=utf-8",
                CacheControl="no-cache, no-store, must-revalidate",
            )
            logger.debug(f"Uploaded s3://{bucket}/{latest_key}")
        except Exception as e:
            logger.error(f"Failed to upload {latest_key}: {e}")
            errors.append(latest_key)

        # archive/DATE/ — one copy per day
        archive_key = f"archive/{today}/{filename}"
        try:
            client.put_object(
                Bucket=bucket,
                Key=archive_key,
                Body=body,
                ContentType="text/html; charset=utf-8",
                CacheControl="no-cache",
            )
            logger.debug(f"Uploaded s3://{bucket}/{archive_key}")
        except Exception as e:
            logger.error(f"Failed to upload {archive_key}: {e}")
            errors.append(archive_key)

    # Upload raw JSON data export
    try:
        json_body = json.dumps(snapshot_data, default=str, indent=2).encode("utf-8")

        client.put_object(
            Bucket=bucket,
            Key="data/latest.json",
            Body=json_body,
            ContentType="application/json",
            CacheControl="no-cache, no-store, must-revalidate",
        )

        client.put_object(
            Bucket=bucket,
            Key=f"data/{today}.json",
            Body=json_body,
            ContentType="application/json",
        )

        logger.debug(f"Uploaded JSON data export to s3://{bucket}/data/")
    except Exception as e:
        logger.error(f"Failed to upload JSON data: {e}")
        errors.append("data/latest.json")

    if errors:
        logger.warning(
            f"Snapshot upload completed with {len(errors)} error(s): "
            f"{', '.join(errors)}"
        )
        return False

    total = len(pages) * 2 + 2  # latest + archive per page + 2 JSON files
    logger.info(
        f"Snapshot uploaded to s3://{bucket}/ — "
        f"{total} objects written"
    )
    logger.info(
        f"Latest snapshot: "
        f"https://{bucket}.s3.ap-south-1.amazonaws.com/latest/index.html"
    )
    return True


def get_snapshot_url() -> str:
    """Return the pre-signed URL for the latest snapshot index page."""
    bucket = _get_bucket()
    if not bucket:
        return ""
    try:
        client = _get_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": "latest/index.html"},
            ExpiresIn=86400,  # 24 hours
        )
        return url
    except Exception as e:
        logger.warning(f"Could not generate pre-signed URL: {e}")
        return ""