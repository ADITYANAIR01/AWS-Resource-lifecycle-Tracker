"""
Base collector class.

All resource-type collectors inherit from BaseCollector.

Each subclass must:
  1. Set RESOURCE_TYPE class attribute (e.g. 'ec2', 'ebs_volume')
  2. Implement the collect() method
  3. Return a list of resource dicts matching the standard schema

Standard resource dict schema:
    {
        "resource_id":        str,
        "resource_type":      str,
        "resource_name":      str | None,
        "account_id":         str,
        "region":             str,
        "state":              str | None,
        "created_at":         datetime | None,
        "tags":               dict,
        "estimated_cost_usd": Decimal,
        "raw_api_response":   dict,
    }
"""

from botocore.config import Config

from utils.logger import get_logger


class BaseCollector:

    RESOURCE_TYPE: str = None

    _BOTO_CONFIG = Config(
        connect_timeout=10,
        read_timeout=30,
        retries={
            "max_attempts": 5,
            "mode": "adaptive",
        },
    )

    def __init__(self, session, account_id: str, region: str):
        if self.RESOURCE_TYPE is None:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set RESOURCE_TYPE"
            )
        self.session    = session
        self.account_id = account_id
        self.region     = region
        self.logger     = get_logger(f"poller.collectors.{self.RESOURCE_TYPE}")

    # -------------------------------------------------------------------------
    # Interface
    # -------------------------------------------------------------------------

    def collect(self) -> list:
        """
        Call the AWS API and return a list of normalised resource dicts.
        Must be implemented by every subclass.
        Must never return None — return [] if no resources found.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement collect()"
        )

    # -------------------------------------------------------------------------
    # boto3 helpers
    # -------------------------------------------------------------------------

    def _make_client(self, service: str):
        """Create a boto3 client with retry + timeout config."""
        return self.session.client(
            service,
            region_name=self.region,
            config=self._BOTO_CONFIG,
        )

    def _make_resource(self, service: str):
        """Create a boto3 resource with retry + timeout config."""
        return self.session.resource(
            service,
            region_name=self.region,
            config=self._BOTO_CONFIG,
        )

    # -------------------------------------------------------------------------
    # Tag helpers
    # -------------------------------------------------------------------------

    def _extract_tags(self, tags_raw: list) -> dict:
        """
        Convert boto3 tag list [{'Key': k, 'Value': v}] to plain dict {k: v}.
        Returns {} if tags_raw is None or empty.
        """
        if not tags_raw:
            return {}
        return {
            t["Key"]: t["Value"]
            for t in tags_raw
            if "Key" in t and "Value" in t
        }

    def _extract_name(self, tags_raw: list, fallback: str) -> str:
        """
        Find the 'Name' tag value from a boto3 tag list.
        Returns fallback (usually the resource ID) if no Name tag exists.
        """
        for tag in (tags_raw or []):
            if tag.get("Key") == "Name":
                return tag.get("Value") or fallback
        return fallback