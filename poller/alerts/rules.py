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

Clock + casing contract (audited — do not "simplify"):
  - last_modified moves ONLY on state change (see insert_or_update_resource
    CASE). The four last_modified age rules below (ec2_stopped_too_long,
    ebs_unattached, rds_stopped_too_long, cloudwatch_alarm_stale) therefore
    measure time-in-state, immune to tag/cost drift. Never rewrite them to
    last_seen or unconditional NOW().
  - iam_user_inactive measures last_activity_at (real IAM activity clock
    written by the IAM collector, migration 001). Rows with NULL activity
    are SUPPRESSED (IS NOT NULL guard) — unknown activity must not alert.
  - State casing: collectors normalise before storing, rules match exactly.
    Lowercase family: ec2 running/stopped, ebs_volume available, rds
    stopped, elastic_ip associated/unassociated, security_group in-use/unused.
    Uppercase family (collector applies .upper(), rules use UPPERCASE):
    cloudwatch_alarm INSUFFICIENT_DATA (raw StateValue), eks PENDING
    (collector uppercases describe_cluster status; if AWS never emits
    PENDING the rule safely never fires), ecs counts-based (no state match).
    Keep rule literals in sync with collector normalisation.
  - Interval params use make_interval(unit => %s) with a plain %s param —
    never INTERVAL '%s days' string interpolation.
"""

import os


def _days(env_var: str, default: int) -> int:
    """Read a threshold from env, return default if not set or invalid."""
    try:
        return int(os.environ.get(env_var, default))
    except ValueError:
        return default


def _minutes(env_var: str, default: int) -> int:
    """Read a minute threshold from env, return default if invalid."""
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
        "type": "ec2_long_running",
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
        "get_params": lambda: (_days("ALERT_EC2_RUNNING_DAYS", 30),),
        "message_fn": lambda row: (
            f"EC2 instance {row['resource_name']} has been running for more than "
            f"{_days('ALERT_EC2_RUNNING_DAYS', 30)} days. "
            f"Verify this is intentional."
        ),
    },
    {
        "type": "ec2_stopped_too_long",
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
        "get_params": lambda: (_days("ALERT_EC2_STOPPED_DAYS", 7),),
        "message_fn": lambda row: (
            f"EC2 instance {row['resource_name']} has been stopped for more than "
            f"{_days('ALERT_EC2_STOPPED_DAYS', 7)} days. "
            f"EBS volumes are still incurring charges. Consider terminating if unused."
        ),
    },
    {
        "type": "ebs_unattached",
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
        "get_params": lambda: (_days("ALERT_EBS_UNATTACHED_DAYS", 7),),
        "message_fn": lambda row: (
            f"EBS volume {row['resource_name']} has been unattached for more than "
            f"{_days('ALERT_EBS_UNATTACHED_DAYS', 7)} days. "
            f"You are being billed for storage with no attached instance."
        ),
    },
    {
        "type": "ebs_snapshot_old",
        "severity": "info",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'ebs_snapshot'
              AND is_active     = TRUE
              AND created_at    < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (_days("ALERT_EBS_SNAPSHOT_AGE_DAYS", 60),),
        "message_fn": lambda row: (
            f"EBS snapshot {row['resource_name']} is more than "
            f"{_days('ALERT_EBS_SNAPSHOT_AGE_DAYS', 60)} days old. "
            f"Review if this snapshot is still needed."
        ),
    },
    {
        "type": "rds_stopped_too_long",
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
        "get_params": lambda: (_days("ALERT_RDS_STOPPED_DAYS", 7),),
        "message_fn": lambda row: (
            f"RDS instance {row['resource_name']} has been stopped for more than "
            f"{_days('ALERT_RDS_STOPPED_DAYS', 7)} days. "
            f"AWS will automatically restart it after 7 days and resume billing."
        ),
    },
    {
        "type": "rds_snapshot_old",
        "severity": "info",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'rds_snapshot'
              AND is_active     = TRUE
              AND created_at    < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (_days("ALERT_RDS_SNAPSHOT_AGE_DAYS", 30),),
        "message_fn": lambda row: (
            f"RDS snapshot {row['resource_name']} is more than "
            f"{_days('ALERT_RDS_SNAPSHOT_AGE_DAYS', 30)} days old. "
            f"Review if this snapshot is still needed."
        ),
    },
    {
        "type": "iam_user_inactive",
        "severity": "warning",
        # Measures the real activity clock (migration 001,
        # resources.last_activity_at, written by the IAM collector from
        # console login / access-key last-used), NOT the row's last_modified.
        # NULL-suppress: users with no observed activity never match, so
        # backfill gaps and never-logged-in service accounts don't alert.
        # Requires migration 001 — on an old DB this rule errors per-cycle
        # and logs via the evaluator instead of firing (fail-silent per
        # rule, never crash the poll). Interval via make_interval(days => %s)
        # with a plain int param (no INTERVAL '%s days' interpolation).
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'iam_user'
              AND is_active     = TRUE
              AND last_activity_at IS NOT NULL
              AND last_activity_at < NOW() - make_interval(days => %s)
        """,
        "get_params": lambda: (_days("ALERT_IAM_INACTIVE_DAYS", 90),),
        "message_fn": lambda row: (
            f"IAM user {row['resource_name']} has had no activity for more than "
            f"{_days('ALERT_IAM_INACTIVE_DAYS', 90)} days. "
            f"Inactive users with active access keys are a security risk."
        ),
    },
    {
        "type": "cloudwatch_alarm_stale",
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
        "get_params": lambda: (_days("ALERT_CW_ALARM_STALE_DAYS", 7),),
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
        "type": "elastic_ip_unassociated",
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
        "type": "security_group_unused",
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
    {
        "type": "ecs_service_unhealthy",
        "severity": "warning",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region,
                   COALESCE(NULLIF(tags->>'_desired_count', '')::INT, 0) AS desired_count,
                   COALESCE(NULLIF(tags->>'_running_count', '')::INT, 0) AS running_count
            FROM resources
            WHERE resource_type = 'ecs'
              AND is_active     = TRUE
              AND COALESCE(NULLIF(tags->>'_desired_count', '')::INT, 0)
                  <> COALESCE(NULLIF(tags->>'_running_count', '')::INT, 0)
              AND COALESCE(last_modified, first_seen)
                  < NOW() - INTERVAL '%s minutes'
        """,
        "get_params": lambda: (_minutes("ALERT_ECS_UNHEALTHY_MINS", 10),),
        "message_fn": lambda row: (
            f"ECS service {row['resource_name']} has desired count "
            f"{row.get('desired_count', 0)} but running count "
            f"{row.get('running_count', 0)} for more than "
            f"{_minutes('ALERT_ECS_UNHEALTHY_MINS', 10)} minutes. "
            f"Investigate task failures or capacity."
        ),
    },
    {
        "type": "eks_cluster_pending",
        "severity": "warning",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'eks'
              AND state         = 'PENDING'
              AND is_active     = TRUE
              AND COALESCE(created_at, first_seen)
                  < NOW() - INTERVAL '%s minutes'
        """,
        "get_params": lambda: (_minutes("ALERT_EKS_PENDING_MINS", 30),),
        "message_fn": lambda row: (
            f"EKS cluster {row['resource_name']} has remained in PENDING state for "
            f"more than {_minutes('ALERT_EKS_PENDING_MINS', 30)} minutes. "
            f"Check control plane and nodegroup provisioning."
        ),
    },
    {
        "type": "cloudfront_disabled",
        "severity": "info",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'cloudfront'
              AND is_active     = TRUE
              AND COALESCE(tags->>'_enabled', 'true') = 'false'
        """,
        "get_params": lambda: (),
        "message_fn": lambda row: (
            f"CloudFront distribution {row['resource_name']} is disabled. "
            f"Confirm this is intentional to avoid stale CDN endpoints."
        ),
    },
    {
        "type": "nat_gateway_active_too_long",
        "severity": "warning",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'nat_gateway'
              AND state         = 'available'
              AND is_active     = TRUE
              AND created_at    < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (_days("ALERT_NAT_GATEWAY_DAYS", 30),),
        "message_fn": lambda row: (
            f"NAT Gateway {row['resource_name'] or row['resource_id']} has been available for more than "
            f"{_days('ALERT_NAT_GATEWAY_DAYS', 30)} days. "
            f"NAT Gateways incur high hourly charges even when idle."
        ),
    },
    {
        "type": "load_balancer_active_too_long",
        "severity": "warning",
        "query": """
            SELECT resource_id, resource_type, resource_name,
                   account_id, region
            FROM resources
            WHERE resource_type = 'load_balancer'
              AND state         = 'active'
              AND is_active     = TRUE
              AND created_at    < NOW() - INTERVAL '%s days'
        """,
        "get_params": lambda: (_days("ALERT_LOAD_BALANCER_DAYS", 30),),
        "message_fn": lambda row: (
            f"Load Balancer {row['resource_name'] or row['resource_id']} has been active for more than "
            f"{_days('ALERT_LOAD_BALANCER_DAYS', 30)} days. "
            f"Verify if it is still routing traffic."
        ),
    },
    # -------------------------------------------------------------------------
    # Tag-based — checked per required tag key
    # These are built dynamically in the evaluator since the required tag
    # list is configurable and can have any number of keys
    # -------------------------------------------------------------------------
    # See evaluator.py — _evaluate_tag_rules() handles these separately
]
