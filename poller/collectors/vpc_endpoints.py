"""
VPC endpoints collector.

Collects VPC endpoints in the configured region and stores them under
resource_type='vpc_endpoint'.

Skips 'deleted' and 'deleting' endpoints.

Cost model (ap-south-1 on-demand approximations):
  Gateway type (S3/DynamoDB) -> $0, no hourly charge
  Interface / GatewayLoadBalancer -> hourly charge from creation time
See utils.cost.estimate_vpc_endpoint_cost.
"""

from collectors.base import BaseCollector
from utils.cost import estimate_vpc_endpoint_cost


class VPCEndpointCollector(BaseCollector):

    RESOURCE_TYPE = "vpc_endpoint"

    _SKIP_STATES = {"deleted", "deleting"}

    def collect(self) -> list:
        client = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting VPC endpoints")

        try:
            paginator = client.get_paginator("describe_vpc_endpoints")

            for page in paginator.paginate():
                for ep in page.get("VpcEndpoints", []):
                    state = ep.get("State", "unknown")
                    if state in self._SKIP_STATES:
                        continue

                    ep_id = ep.get("VpcEndpointId")
                    if not ep_id:
                        continue

                    tags_raw = ep.get("Tags", [])
                    tags = self._extract_tags(tags_raw)
                    name = self._extract_name(tags_raw, ep_id)

                    ep_type = ep.get("VpcEndpointType", "unknown")
                    service = ep.get("ServiceName", "")
                    created_at = ep.get("CreationTimestamp")
                    cost = estimate_vpc_endpoint_cost(ep_type, created_at)

                    tags.update(
                        {
                            "_vpc_id": ep.get("VpcId", ""),
                            "_endpoint_type": ep_type,
                            "_service_name": service,
                        }
                    )

                    resources.append(
                        {
                            "resource_id": ep_id,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": name,
                            "account_id": self.account_id,
                            "region": self.region,
                            "state": state,
                            "created_at": created_at,
                            "tags": tags,
                            "estimated_cost_usd": cost,
                            "raw_api_response": ep,
                        }
                    )

        except Exception as e:
            self.logger.error(f"VPC endpoint collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} VPC endpoint(s)")
        return resources
