"""
Internet gateways collector.

Collects internet gateways in the configured region and stores them
under resource_type='internet_gateway'.

State derivation (no state field in the EC2 API):
  attached -> attached to at least one VPC
  detached -> no attachments (unused, safe to delete)

Internet gateways have no creation timestamp — created_at is None.
No hourly charge — estimated_cost_usd is 0.
"""

from collectors.base import BaseCollector


class InternetGatewayCollector(BaseCollector):

    RESOURCE_TYPE = "internet_gateway"

    def collect(self) -> list:
        client = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting internet gateways")

        try:
            paginator = client.get_paginator("describe_internet_gateways")

            for page in paginator.paginate():
                for igw in page.get("InternetGateways", []):
                    igw_id = igw.get("InternetGatewayId")
                    if not igw_id:
                        continue

                    tags_raw = igw.get("Tags", [])
                    tags = self._extract_tags(tags_raw)
                    name = self._extract_name(tags_raw, igw_id)

                    attachments = igw.get("Attachments", [])
                    attached = any(
                        a.get("State") in ("attached", "available")
                        for a in attachments
                    )
                    state = "attached" if attached else "detached"
                    vpc_ids = ",".join(
                        sorted(
                            {
                                a.get("VpcId", "")
                                for a in attachments
                                if a.get("VpcId")
                            }
                        )
                    )

                    tags.update(
                        {
                            "_vpc_ids": vpc_ids,
                            "_attachment_count": str(len(attachments)),
                        }
                    )

                    resources.append(
                        {
                            "resource_id": igw_id,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": name,
                            "account_id": self.account_id,
                            "region": self.region,
                            "state": state,
                            "created_at": None,
                            "tags": tags,
                            "estimated_cost_usd": 0,
                            "raw_api_response": igw,
                        }
                    )

        except Exception as e:
            self.logger.error(f"Internet gateway collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} internet gateway(s)")
        return resources
