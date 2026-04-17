"""
NAT Gateway collector.

Collects NAT gateways in the configured region and stores them under
resource_type='nat_gateway'.
"""

from collectors.base import BaseCollector
from utils.cost import estimate_nat_gateway_cost


class NatGatewayCollector(BaseCollector):

    RESOURCE_TYPE = "nat_gateway"

    def collect(self) -> list:
        client = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting NAT gateways")

        try:
            paginator = client.get_paginator("describe_nat_gateways")

            for page in paginator.paginate():
                for nat in page.get("NatGateways", []):
                    state = nat.get("State", "unknown")
                    if state == "deleted":
                        continue

                    nat_id = nat.get("NatGatewayId")
                    tags_raw = nat.get("Tags", [])
                    tags = self._extract_tags(tags_raw)

                    addresses = nat.get("NatGatewayAddresses", [])
                    public_ip = addresses[0].get("PublicIp") if addresses else ""
                    private_ip = addresses[0].get("PrivateIp") if addresses else ""

                    name = self._extract_name(tags_raw, public_ip or nat_id)
                    created_at = nat.get("CreateTime")

                    tags.update(
                        {
                            "_subnet_id": nat.get("SubnetId", ""),
                            "_vpc_id": nat.get("VpcId", ""),
                            "_connectivity_type": nat.get("ConnectivityType", "public"),
                            "_public_ip": public_ip,
                            "_private_ip": private_ip,
                        }
                    )

                    resources.append(
                        {
                            "resource_id": nat_id,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": name,
                            "account_id": self.account_id,
                            "region": self.region,
                            "state": state,
                            "created_at": created_at,
                            "tags": tags,
                            "estimated_cost_usd": estimate_nat_gateway_cost(created_at),
                            "raw_api_response": nat,
                        }
                    )

        except Exception as e:
            self.logger.error(f"NAT gateway collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} NAT gateway(s)")
        return resources
