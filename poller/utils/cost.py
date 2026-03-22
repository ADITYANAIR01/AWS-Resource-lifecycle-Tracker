"""
Cost estimation for AWS resources.

All estimates are based on ap-south-1 (Mumbai) on-demand pricing.
These are APPROXIMATIONS only — they do not reflect:
  - Reserved Instances or Savings Plans
  - Spot pricing
  - Data transfer costs
  - Free tier credits

Always check AWS Cost Explorer for actual billing.
"""

from datetime import datetime, timezone
from decimal import Decimal

from utils.logger import get_logger

logger = get_logger("poller.utils.cost")

# ---------------------------------------------------------------------------
# EC2 on-demand hourly rates — ap-south-1 (USD)
# ---------------------------------------------------------------------------
EC2_HOURLY_RATES = {
    # T2 family
    "t2.nano":     Decimal("0.0058"),
    "t2.micro":    Decimal("0.0116"),
    "t2.small":    Decimal("0.0232"),
    "t2.medium":   Decimal("0.0464"),
    "t2.large":    Decimal("0.0928"),
    "t2.xlarge":   Decimal("0.1856"),
    "t2.2xlarge":  Decimal("0.3712"),
    # T3 family
    "t3.nano":     Decimal("0.0052"),
    "t3.micro":    Decimal("0.0104"),
    "t3.small":    Decimal("0.0208"),
    "t3.medium":   Decimal("0.0416"),
    "t3.large":    Decimal("0.0832"),
    "t3.xlarge":   Decimal("0.1664"),
    "t3.2xlarge":  Decimal("0.3328"),
    # T3a family
    "t3a.nano":    Decimal("0.0047"),
    "t3a.micro":   Decimal("0.0094"),
    "t3a.small":   Decimal("0.0188"),
    "t3a.medium":  Decimal("0.0376"),
    "t3a.large":   Decimal("0.0752"),
    # M5 family
    "m5.large":    Decimal("0.0960"),
    "m5.xlarge":   Decimal("0.1920"),
    "m5.2xlarge":  Decimal("0.3840"),
    "m5.4xlarge":  Decimal("0.7680"),
    # M6i family
    "m6i.large":   Decimal("0.1010"),
    "m6i.xlarge":  Decimal("0.2020"),
    "m6i.2xlarge": Decimal("0.4040"),
    # C5 family
    "c5.large":    Decimal("0.0850"),
    "c5.xlarge":   Decimal("0.1700"),
    "c5.2xlarge":  Decimal("0.3400"),
    "c5.4xlarge":  Decimal("0.6800"),
    # C6i family
    "c6i.large":   Decimal("0.0890"),
    "c6i.xlarge":  Decimal("0.1780"),
    # R5 family
    "r5.large":    Decimal("0.1260"),
    "r5.xlarge":   Decimal("0.2520"),
    "r5.2xlarge":  Decimal("0.5040"),
    # R6i family
    "r6i.large":   Decimal("0.1320"),
    "r6i.xlarge":  Decimal("0.2640"),
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


def _hours_since(dt: datetime) -> Decimal:
    """Calculate hours elapsed since a datetime. Returns 0 if dt is None."""
    if dt is None:
        return Decimal("0")
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elapsed = now - dt
    hours = elapsed.total_seconds() / 3600
    return Decimal(str(round(max(hours, 0), 4)))


def _days_since(dt: datetime) -> Decimal:
    """Calculate days elapsed since a datetime. Returns 0 if dt is None."""
    if dt is None:
        return Decimal("0")
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    elapsed = now - dt
    days = elapsed.total_seconds() / 86400
    return Decimal(str(round(max(days, 0), 4)))


def estimate_ec2_cost(instance_type: str, launch_time: datetime) -> Decimal:
    """
    Estimate total EC2 cost since launch.
    Returns 0 with a warning if instance type is not in the rate table.
    """
    rate = EC2_HOURLY_RATES.get(instance_type)
    if rate is None:
        logger.warning(
            f"No hourly rate for instance type '{instance_type}' — cost set to 0. "
            f"Add it to EC2_HOURLY_RATES in cost.py"
        )
        return Decimal("0")
    hours = _hours_since(launch_time)
    return round(rate * hours, 4)


def estimate_ebs_volume_cost(size_gb: int, volume_type: str, create_time: datetime) -> Decimal:
    """
    Estimate total EBS volume cost since creation.
    Formula: GB x days_alive x (monthly_rate / 30)
    """
    rate = EBS_MONTHLY_RATE_PER_GB.get(volume_type)
    if rate is None:
        logger.warning(
            f"No monthly rate for EBS type '{volume_type}' — cost set to 0. "
            f"Add it to EBS_MONTHLY_RATE_PER_GB in cost.py"
        )
        return Decimal("0")
    days = _days_since(create_time)
    daily_rate = rate / Decimal("30")
    return round(Decimal(str(size_gb)) * days * daily_rate, 4)


def estimate_ebs_snapshot_cost(size_gb: int, start_time: datetime) -> Decimal:
    """
    Estimate total EBS snapshot storage cost since creation.
    Formula: GB x days_alive x (snapshot_rate / 30)
    """
    days = _days_since(start_time)
    daily_rate = EBS_SNAPSHOT_RATE_PER_GB / Decimal("30")
    return round(Decimal(str(size_gb)) * days * daily_rate, 4)


def estimate_elastic_ip_cost(unassociated_since: datetime) -> Decimal:
    """
    Estimate cost of an unassociated Elastic IP.
    AWS charges $0.005/hr for unassociated EIPs.
    """
    hours = _hours_since(unassociated_since)
    return round(ELASTIC_IP_HOURLY_RATE * hours, 4)