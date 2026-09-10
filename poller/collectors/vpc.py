"""
VPC collector.

Collects VPCs in the configured region and stores them under
resource_type='vpc'.

VPCs have no creation timestamp in the EC2 API — created_at is None.
VPCs themselves incur no hourly charge — estimated_cost_usd is 0.
"""

from collectors.base import BaseCollector


class VPCCollector(BaseCollector):

    RESOURCE_TYPE = "vpc"

    def collect(self) -> list:
        client = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting VPCs")

        try:
            paginator = client.get_paginator("describe_vpcs")

            for page in paginator.paginate():
                for vpc in page.get("Vpcs", []):
                    vpc_id = vpc.get("VpcId")
                    if not vpc_id:
                        continue

                    state = vpc.get("State", "unknown")
                    tags_raw = vpc.get("Tags", [])
                    tags = self._extract_tags(tags_raw)
                    name = self._extract_name(tags_raw, vpc_id)

                    is_default = bool(vpc.get("IsDefault", False))
                    tags.update(
                        {
                            "_cidr_block": vpc.get("CidrBlock", ""),
                            "_is_default": "true" if is_default else "false",
                            "_dhcp_options_id": vpc.get("DhcpOptionsId", ""),
                            "_tenancy": vpc.get("InstanceTenancy", ""),
                        }
                    )

                    resources.append(
                        {
                            "resource_id": vpc_id,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": name,
                            "account_id": self.account_id,
                            "region": self.region,
                            "state": state,
                            "created_at": None,
                            "tags": tags,
                            "estimated_cost_usd": 0,
                            "raw_api_response": vpc,
                        }
                    )

        except Exception as e:
            self.logger.error(f"VPC collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} VPC(s)")
        return resources
