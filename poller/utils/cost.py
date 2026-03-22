"""
Cost estimation for AWS resources.

All estimates are based on ap-south-1 (Mumbai) on-demand pricing.
These are APPROXIMATIONS only — they do not reflect:
  - Reserved Instances or Savings Plans
  - Spot pricing
  - Data transfer costs
  - Free tier credits

Always check AWS Cost Explorer for actual billing.
S3 cost estimation is not available in v1 — requires Storage Lens.
"""

from datetime import datetime, timezone
from decimal import Decimal

from utils.logger import get_logger

logger = get_logger("poller.utils.cost")

# ---------------------------------------------------------------------------
# EC2 on-demand hourly rates — ap-south-1 (USD)
# ---------------------------------------------------------------------------
EC2_HOURLY_RATES = {
    "t2.nano":     Decimal("0.0058"),
    "t2.micro":    Decimal("0.0116"),
    "t2.small":    Decimal("0.0232"),
    "t2.medium":   Decimal("0.0464"),
    "t2.large":    Decimal("0.0928"),
    "t2.xlarge":   Decimal("0.1856"),
    "t2.2xlarge":  Decimal("0.3712"),
    "t3.nano":     Decimal("0.0052"),
    "t3.micro":    Decimal("0.0104"),
    "t3.small":    Decimal("0.0208"),
    "t3.medium":   Decimal("0.0416"),
    "t3.large":    Decimal("0.0832"),
    "t3.xlarge":   Decimal("0.1664"),
    "t3.2xlarge":  Decimal("0.3328"),
    "t3a.nano":    Decimal("0.0047"),
    "t3a.micro":   Decimal("0.0094"),
    "t3a.small":   Decimal("0.0188"),
    "t3a.medium":  Decimal("0.0376"),
    "t3a.large":   Decimal("0.0752"),
    "m5.large":    Decimal("0.0960"),
    "m5.xlarge":   Decimal("0.1920"),
    "m5.2xlarge":  Decimal("0.3840"),
    "m5.4xlarge":  Decimal("0.7680"),
    "m6i.large":   Decimal("0.1010"),
    "m6i.xlarge":  Decimal("0.2020"),
    "m6i.2xlarge": Decimal("0.4040"),
    "c5.large":    Decimal("0.0850"),
    "c5.xlarge":   Decimal("0.1700"),
    "c5.2xlarge":  Decimal("0.3400"),
    "c5.4xlarge":  Decimal("0.6800"),
    "c6i.large":   Decimal("0.0890"),
    "c6i.xlarge":  Decimal("0.1780"),
    "r5.large":    Decimal("0.1260"),
    "r5.xlarge":   Decimal("0.2520"),
    "r5.2xlarge":  Decimal("0.5040"),
    "r6i.large":   Decimal("0.1320"),
    "r6i.xlarge":  Decimal("0.2640"),
}

# ---------------------------------------------------------------------------
# RDS on-demand hourly rates — ap-south-1 (USD)
# ---------------------------------------------------------------------------
RDS_HOURLY_RATES = {
    "db.t3.micro":    Decimal("0.017"),
    "db.t3.small":    Decimal("0.034"),
    "db.t3.medium":   Decimal("0.068"),
    "db.t3.large":    Decimal("0.136"),
    "db.t3.xlarge":   Decimal("0.272"),
    "db.t3.2xlarge":  Decimal("0.544"),
    "db.t4g.micro":   Decimal("0.016"),
    "db.t4g.small":   Decimal("0.032"),
    "db.t4g.medium":  Decimal("0.064"),
    "db.t4g.large":   Decimal("0.128"),
    "db.m5.large":    Decimal("0.171"),
    "db.m5.xlarge":   Decimal("0.342"),
    "db.m5.2xlarge":  Decimal("0.684"),
    "db.m5.4xlarge":  Decimal("1.368"),
    "db.m6g.large":   Decimal("0.156"),
    "db.m6g.xlarge":  Decimal("0.312"),
    "db.r5.large":    Decimal("0.240"),
    "db.r5.xlarge":   Decimal("0.480"),
    "db.r5.2xlarge":  Decimal("0.960"),
    "db.r6g.large":   Decimal("0.216"),
    "db.r6g.xlarge":  Decimal("0.432"),
}

# ---------------------------------------------------------------------------
# EBS monthly rates per GB — ap-south-1 (USD)
# ---------------------------------------------------------------------------
EBS_MONTHLY_RATE_PER_GB = {
    "gp2":      Decimal("0.10"),
    "gp3":      Decimal("0.08"),
    "io1":      Decimal("0.125"),
    "io2":      Decimal("0.125"),
    "st1":      Decimal("0.045"),
    "sc1":      Decimal("0.025"),
    "standard": Decimal("0.05"),
}

EBS_SNAPSHOT_RATE_PER_GB = Decimal("0.05")
ELASTIC_IP_HOURLY_RATE   = Decimal("0.005")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hours_since(dt: datetime) -> Decimal:
    """Hours elapsed since a datetime. Returns 0 if dt is None."""
    if dt is None:
        return Decimal("0")
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elapsed = now - dt
    return Decimal(str(round(max(elapsed.total_seconds() / 3600, 0), 4)))


def _days_since(dt: datetime) -> Decimal:
    """Days elapsed since a datetime. Returns 0 if dt is None."""
    if dt is None:
        return Decimal("0")
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elapsed = now - dt
    return Decimal(str(round(max(elapsed.total_seconds() / 86400, 0), 4)))


# ---------------------------------------------------------------------------
# Estimation functions
# ---------------------------------------------------------------------------

def estimate_ec2_cost(instance_type: str, launch_time: datetime) -> Decimal:
    rate = EC2_HOURLY_RATES.get(instance_type)
    if rate is None:
        logger.warning(
            f"No hourly rate for EC2 type '{instance_type}' — cost set to 0"
        )
        return Decimal("0")
    return round(rate * _hours_since(launch_time), 4)


def estimate_rds_cost(db_class: str, create_time: datetime) -> Decimal:
    rate = RDS_HOURLY_RATES.get(db_class)
    if rate is None:
        logger.warning(
            f"No hourly rate for RDS class '{db_class}' — cost set to 0"
        )
        return Decimal("0")
    return round(rate * _hours_since(create_time), 4)


def estimate_ebs_volume_cost(
    size_gb: int, volume_type: str, create_time: datetime
) -> Decimal:
    rate = EBS_MONTHLY_RATE_PER_GB.get(volume_type)
    if rate is None:
        logger.warning(
            f"No monthly rate for EBS type '{volume_type}' — cost set to 0"
        )
        return Decimal("0")
    daily_rate = rate / Decimal("30")
    return round(Decimal(str(size_gb)) * _days_since(create_time) * daily_rate, 4)


def estimate_ebs_snapshot_cost(size_gb: int, start_time: datetime) -> Decimal:
    daily_rate = EBS_SNAPSHOT_RATE_PER_GB / Decimal("30")
    return round(Decimal(str(size_gb)) * _days_since(start_time) * daily_rate, 4)


def estimate_elastic_ip_cost() -> Decimal:
    """
    Estimate ongoing cost of an unassociated Elastic IP.
    AWS charges $0.005/hr — we estimate based on 1 hour as a floor.
    Actual duration tracked via last_modified in the DB.
    """
    return round(ELASTIC_IP_HOURLY_RATE, 4)