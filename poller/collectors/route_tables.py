"""
Route tables collector.

Collects route tables in the configured region and stores them under
resource_type='route_table'.

State derivation (no state field in the EC2 API):
  main         -> the table is a VPC's main route table
  associated   -> explicitly associated with at least one subnet/gateway
  unassociated -> no associations at all (custom table not in use)

Route tables have no creation timestamp — created_at is None.
No hourly charge — estimated_cost_usd is 0.
"""

from collectors.base import BaseCollector


class RouteTableCollector(BaseCollector):

    RESOURCE_TYPE = "route_table"

    def collect(self) -> list:
        client = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting route tables")

        try:
            paginator = client.get_paginator("describe_route_tables")

            for page in paginator.paginate():
                for rt in page.get("RouteTables", []):
                    rt_id = rt.get("RouteTableId")
                    if not rt_id:
                        continue

                    tags_raw = rt.get("Tags", [])
                    tags = self._extract_tags(tags_raw)
                    name = self._extract_name(tags_raw, rt_id)

                    associations = rt.get("Associations", [])
                    is_main = any(a.get("Main", False) for a in associations)
                    if is_main:
                        state = "main"
                    elif associations:
                        state = "associated"
                    else:
                        state = "unassociated"

                    tags.update(
                        {
                            "_vpc_id": rt.get("VpcId", ""),
                            "_is_main": "true" if is_main else "false",
                            "_association_count": str(len(associations)),
                            "_route_count": str(len(rt.get("Routes", []))),
                        }
                    )

                    resources.append(
                        {
                            "resource_id": rt_id,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": name,
                            "account_id": self.account_id,
                            "region": self.region,
                            "state": state,
                            "created_at": None,
                            "tags": tags,
                            "estimated_cost_usd": 0,
                            "raw_api_response": rt,
                        }
                    )

        except Exception as e:
            self.logger.error(f"Route table collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} route table(s)")
        return resources
