"""
Subnets collector.

Collects subnets in the configured region and stores them under
resource_type='subnet'.

Subnets have no creation timestamp in the EC2 API — created_at is None.
Subnets themselves incur no hourly charge — estimated_cost_usd is 0.
"""

from collectors.base import BaseCollector


class SubnetCollector(BaseCollector):

    RESOURCE_TYPE = "subnet"

    def collect(self) -> list:
        client = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting subnets")

        try:
            paginator = client.get_paginator("describe_subnets")

            for page in paginator.paginate():
                for subnet in page.get("Subnets", []):
                    subnet_id = subnet.get("SubnetId")
                    if not subnet_id:
                        continue

                    state = subnet.get("State", "unknown")
                    tags_raw = subnet.get("Tags", [])
                    tags = self._extract_tags(tags_raw)
                    name = self._extract_name(tags_raw, subnet_id)

                    tags.update(
                        {
                            "_vpc_id": subnet.get("VpcId", ""),
                            "_cidr_block": subnet.get("CidrBlock", ""),
                            "_availability_zone": subnet.get("AvailabilityZone", ""),
                            "_available_ips": str(
                                subnet.get("AvailableIpAddressCount", "")
                            ),
                            "_default_for_az": (
                                "true"
                                if subnet.get("DefaultForAz", False)
                                else "false"
                            ),
                        }
                    )

                    resources.append(
                        {
                            "resource_id": subnet_id,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": name,
                            "account_id": self.account_id,
                            "region": self.region,
                            "state": state,
                            "created_at": None,
                            "tags": tags,
                            "estimated_cost_usd": 0,
                            "raw_api_response": subnet,
                        }
                    )

        except Exception as e:
            self.logger.error(f"Subnet collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} subnet(s)")
        return resources
