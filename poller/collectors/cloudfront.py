"""
CloudFront distributions collector.

CloudFront is a global service. Resources are always stored with region='global'.

Internal metadata stored in tags for alerting/analytics:
  - _enabled
  - _origin_count
  - _status
"""

from datetime import timezone
from decimal import Decimal

from collectors.base import BaseCollector


class CloudFrontCollector(BaseCollector):

    RESOURCE_TYPE = "cloudfront"

    _DAILY_PLACEHOLDER_COST_USD = Decimal("0.01")

    def collect(self) -> list:
        # CloudFront is global. Build the client without region pinning.
        client = self.session.client("cloudfront", config=self._BOTO_CONFIG)
        resources = []

        self.logger.info("Collecting CloudFront distributions")

        try:
            paginator = client.get_paginator("list_distributions")

            for page in paginator.paginate():
                distribution_list = page.get("DistributionList", {})
                for distribution in distribution_list.get("Items", []):
                    dist_id = distribution.get("Id")
                    dist_arn = distribution.get("ARN", "")
                    domain_name = distribution.get("DomainName", "")
                    status = distribution.get("Status", "InProgress")
                    enabled = bool(distribution.get("Enabled", False))
                    origins = distribution.get("Origins", {}).get("Items", [])
                    created_at = self._ensure_utc(distribution.get("LastModifiedTime"))

                    tags = self._fetch_distribution_tags(client, dist_arn)
                    tags.update(
                        {
                            "_enabled": "true" if enabled else "false",
                            "_origin_count": str(len(origins)),
                            "_status": status,
                        }
                    )

                    raw = {
                        "distribution": distribution,
                        "origin_count": len(origins),
                        "enabled": enabled,
                    }

                    resources.append(
                        {
                            "resource_id": dist_arn or dist_id,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": domain_name or dist_id,
                            "account_id": self.account_id,
                            "region": "global",
                            "state": status,
                            "created_at": created_at,
                            "tags": tags,
                            "estimated_cost_usd": self._DAILY_PLACEHOLDER_COST_USD,
                            "raw_api_response": raw,
                        }
                    )

        except Exception as e:
            self.logger.error(f"CloudFront collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} CloudFront distribution(s)")
        return resources

    def _fetch_distribution_tags(self, client, distribution_arn: str) -> dict:
        if not distribution_arn:
            return {}

        try:
            response = client.list_tags_for_resource(Resource=distribution_arn)
            tags_raw = response.get("Tags", {}).get("Items", [])
            return self._extract_tags(tags_raw)
        except Exception as e:
            self.logger.warning(
                f"Could not fetch tags for CloudFront distribution {distribution_arn}: {e}"
            )
            return {}

    def _ensure_utc(self, dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
