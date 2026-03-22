"""
Alert rule definitions.

Each rule is a dict:
    type        → unique string key (used for deduplication in DB)
    severity    → 'info' | 'warning' | 'critical'
    query       → SQL that returns (resource_id, resource_type,
                  resource_name, account_id, region) for matching resources
    get_params  → callable returning tuple of query params (reads from os.environ)
    message_fn  → callable(row) returning the alert message string

All thresholds read from environment variables with safe defaults.
Changing thresholds requires only a .env update — no code change.
"""

import os


def _days(env_var: str, default: int) -> int:
    """Read a threshold from env, return default if not set or invalid."""
    try:
        return int(os.environ.get(env_var, default))
    except ValueError:
        return default


def _required_tags() -> list:
    """Read required tag keys from env."""
    raw = os.environ.get("REQUIRED_TAGS", "Owner,Project,Environment")
    return [t.strip() for t in raw.split(",") if t.strip()]


# =============================================================================
# All alert rules
# =============================================================================

ALERT_RULES = [

    # -------------------------------------------------------------------------
    # Age-based
    # -------------------------------------------------------------------------

    {
        "type":     "ec2_long_running",
        "severity": "warning",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'ec2'
              AND state         = 'running'
              AND is_active     = TRUE
              AND created_at    < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (
            _days("ALERT_EC2_RUNNING_DAYS", 30),
        ),
        "message_fn": lambda row: (
            f"EC2 instance {row['resource_name']} has been running for more than "
            f"{_days('ALERT_EC2_RUNNING_DAYS', 30)} days. "
            f"Verify this is intentional."
        ),
    },

    {
        "type":     "ec2_stopped_too_long",
        "severity": "info",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'ec2'
              AND state         = 'stopped'
              AND is_active     = TRUE
              AND last_modified < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (
            _days("ALERT_EC2_STOPPED_DAYS", 7),
        ),
        "message_fn": lambda row: (
            f"EC2 instance {row['resource_name']} has been stopped for more than "
            f"{_days('ALERT_EC2_STOPPED_DAYS', 7)} days. "
            f"EBS volumes are still incurring charges. Consider terminating if unused."
        ),
    },

    {
        "type":     "ebs_unattached",
        "severity": "warning",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'ebs_volume'
              AND state         = 'available'
              AND is_active     = TRUE
              AND last_modified < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (
            _days("ALERT_EBS_UNATTACHED_DAYS", 7),
        ),
        "message_fn": lambda row: (
            f"EBS volume {row['resource_name']} has been unattached for more than "
            f"{_days('ALERT_EBS_UNATTACHED_DAYS', 7)} days. "
            f"You are being billed for storage with no attached instance."
        ),
    },

    {
        "type":     "ebs_snapshot_old",
        "severity": "info",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'ebs_snapshot'
              AND is_active     = TRUE
              AND created_at    < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (
            _days("ALERT_EBS_SNAPSHOT_AGE_DAYS", 60),
        ),
        "message_fn": lambda row: (
            f"EBS snapshot {row['resource_name']} is more than "
            f"{_days('ALERT_EBS_SNAPSHOT_AGE_DAYS', 60)} days old. "
            f"Review if this snapshot is still needed."
        ),
    },

    {
        "type":     "rds_stopped_too_long",
        "severity": "critical",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'rds'
              AND state         = 'stopped'
              AND is_active     = TRUE
              AND last_modified < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (
            _days("ALERT_RDS_STOPPED_DAYS", 7),
        ),
        "message_fn": lambda row: (
            f"RDS instance {row['resource_name']} has been stopped for more than "
            f"{_days('ALERT_RDS_STOPPED_DAYS', 7)} days. "
            f"AWS will automatically restart it after 7 days and resume billing."
        ),
    },

    {
        "type":     "rds_snapshot_old",
        "severity": "info",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'rds_snapshot'
              AND is_active     = TRUE
              AND created_at    < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (
            _days("ALERT_RDS_SNAPSHOT_AGE_DAYS", 30),
        ),
        "message_fn": lambda row: (
            f"RDS snapshot {row['resource_name']} is more than "
            f"{_days('ALERT_RDS_SNAPSHOT_AGE_DAYS', 30)} days old. "
            f"Review if this snapshot is still needed."
        ),
    },

    {
        "type":     "iam_user_inactive",
        "severity": "warning",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'iam_user'
              AND is_active     = TRUE
              AND (
                  last_modified IS NULL
                  OR last_modified < NOW() - INTERVAL '%s days'
              )
        """,
        "get_params": lambda: (
            _days("ALERT_IAM_INACTIVE_DAYS", 90),
        ),
        "message_fn": lambda row: (
            f"IAM user {row['resource_name']} has had no activity for more than "
            f"{_days('ALERT_IAM_INACTIVE_DAYS', 90)} days. "
            f"Inactive users with active access keys are a security risk."
        ),
    },

    {
        "type":     "cloudwatch_alarm_stale",
        "severity": "info",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'cloudwatch_alarm'
              AND state         = 'INSUFFICIENT_DATA'
              AND is_active     = TRUE
              AND last_modified < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (
            _days("ALERT_CW_ALARM_STALE_DAYS", 7),
        ),
        "message_fn": lambda row: (
            f"CloudWatch alarm {row['resource_name']} has been in "
            f"INSUFFICIENT_DATA state for more than "
            f"{_days('ALERT_CW_ALARM_STALE_DAYS', 7)} days. "
            f"The metric it monitors may no longer exist."
        ),
    },

    # -------------------------------------------------------------------------
    # State-based
    # -------------------------------------------------------------------------

    {
        "type":     "elastic_ip_unassociated",
        "severity": "critical",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'elastic_ip'
              AND state         = 'unassociated'
              AND is_active     = TRUE
        """,
        "get_params": lambda: (),
        "message_fn": lambda row: (
            f"Elastic IP {row['resource_name']} is unassociated. "
            f"AWS charges $0.005/hr for unassociated Elastic IPs. "
            f"Associate it or release it to stop charges."
        ),
    },

    {
        "type":     "security_group_unused",
        "severity": "info",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'security_group'
              AND state         = 'unused'
              AND is_active     = TRUE
        """,
        "get_params": lambda: (),
        "message_fn": lambda row: (
            f"Security group {row['resource_name']} is not attached to any "
            f"resource. Unused security groups clutter your environment "
            f"and make auditing harder."
        ),
    },

    # -------------------------------------------------------------------------
    # Tag-based — checked per required tag key
    # These are built dynamically in the evaluator since the required tag
    # list is configurable and can have any number of keys
    # -------------------------------------------------------------------------
    # See evaluator.py — _evaluate_tag_rules() handles these separately
]