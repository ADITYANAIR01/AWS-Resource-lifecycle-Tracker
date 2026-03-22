"""
SNS notification sender.

Sends alert emails via AWS SNS.
One function: send_alert() — takes an alert dict, formats it,
publishes to the configured SNS topic.

Never raises — SNS failures are logged but never crash the evaluator.
The alert is still marked in the DB even if SNS send fails,
so it will be retried on the next poll cycle.
"""

import os

import boto3
from botocore.config import Config

from utils.logger import get_logger

logger = get_logger("poller.notifier.sns")

_BOTO_CONFIG = Config(
    connect_timeout=10,
    read_timeout=30,
    retries={"max_attempts": 3, "mode": "adaptive"},
)


def send_alert(alert: dict) -> bool:
    """
    Send an SNS email notification for an alert.

    alert dict must contain:
        id, alert_type, severity, resource_id, resource_type,
        resource_name, account_id, region, message

    Returns True if sent successfully, False if SNS call failed.
    """
    topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    region    = os.environ.get("AWS_REGION", "ap-south-1")

    if not topic_arn:
        logger.warning(
            "SNS_TOPIC_ARN not set — alert not sent. "
            "Set SNS_TOPIC_ARN in .env to enable email notifications."
        )
        return False

    subject = _build_subject(alert)
    message = _build_message(alert)

    try:
        client = boto3.client(
            "sns",
            region_name=region,
            config=_BOTO_CONFIG,
        )
        client.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=message,
        )
        logger.info(
            f"SNS alert sent — type={alert['alert_type']} "
            f"resource={alert.get('resource_name', alert['resource_id'])} "
            f"severity={alert['severity']}"
        )
        return True

    except Exception as e:
        logger.error(
            f"SNS send failed for alert_type={alert['alert_type']} "
            f"resource={alert.get('resource_name', alert['resource_id'])}: {e}"
        )
        return False


def send_resolution(alert: dict) -> bool:
    """
    Send an SNS notification when an alert auto-resolves.
    """
    topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    region    = os.environ.get("AWS_REGION", "ap-south-1")

    if not topic_arn:
        return False

    subject = f"[RESOLVED] {alert['alert_type'].replace('_', ' ').title()}"
    message = (
        f"RESOLVED — {alert['alert_type'].replace('_', ' ').title()}\n\n"
        f"Resource: {alert.get('resource_name', alert['resource_id'])} "
        f"({alert['resource_type']})\n"
        f"Account:  {alert.get('account_id', 'unknown')}\n"
        f"Region:   {alert.get('region', 'unknown')}\n\n"
        f"The alert condition is no longer true.\n"
        f"Original message: {alert['message']}\n\n"
        f"---\nAWS Resource Lifecycle Tracker"
    )

    try:
        client = boto3.client(
            "sns",
            region_name=region,
            config=_BOTO_CONFIG,
        )
        client.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=message,
        )
        logger.info(
            f"SNS resolution sent — type={alert['alert_type']} "
            f"resource={alert.get('resource_name', alert['resource_id'])}"
        )
        return True
    except Exception as e:
        logger.error(f"SNS resolution send failed: {e}")
        return False


def send_poller_failure(status: str, error_log: str) -> bool:
    """
    Send an SNS notification when the poller itself fails or partially fails.
    """
    topic_arn = os.environ.get("SNS_TOPIC_ARN", "")
    region    = os.environ.get("AWS_REGION", "ap-south-1")

    if not topic_arn:
        return False

    subject = f"[{status.upper()}] AWS Resource Lifecycle Tracker — Poller Issue"
    message = (
        f"Poller Status: {status}\n\n"
        f"Error details:\n{error_log}\n\n"
        f"---\nAWS Resource Lifecycle Tracker"
    )

    try:
        client = boto3.client(
            "sns",
            region_name=region,
            config=_BOTO_CONFIG,
        )
        client.publish(
            TopicArn=topic_arn,
            Subject=subject,
            Message=message,
        )
        return True
    except Exception as e:
        logger.error(f"SNS poller failure send failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_subject(alert: dict) -> str:
    severity = alert["severity"].upper()
    alert_type = alert["alert_type"].replace("_", " ").title()
    resource = alert.get("resource_name", alert["resource_id"])
    return f"[{severity}] {alert_type} — {resource}"


def _build_message(alert: dict) -> str:
    severity    = alert["severity"].upper()
    alert_type  = alert["alert_type"].replace("_", " ").title()
    resource_id = alert["resource_id"]
    resource    = alert.get("resource_name", resource_id)
    rtype       = alert["resource_type"]
    account     = alert.get("account_id", "unknown")
    region      = alert.get("region", "unknown")
    message     = alert["message"]
    alert_id    = alert.get("id", "")

    return (
        f"[{severity}] {alert_type}\n\n"
        f"Resource: {resource} ({rtype})\n"
        f"ID:       {resource_id}\n"
        f"Account:  {account}\n"
        f"Region:   {region}\n\n"
        f"{message}\n\n"
        f"---\n"
        f"AWS Resource Lifecycle Tracker\n"
        f"Acknowledge: python manage.py alerts acknowledge {alert_id}"
    )