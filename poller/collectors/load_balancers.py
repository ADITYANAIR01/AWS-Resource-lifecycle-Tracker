"""
Elastic Load Balancers collector (ALB/NLB/GLB).

Collects ELBv2 load balancers in the configured region and stores them
under resource_type='load_balancer'.
"""

from collectors.base import BaseCollector
from utils.cost import estimate_load_balancer_cost


class LoadBalancerCollector(BaseCollector):

    RESOURCE_TYPE = "load_balancer"

    def collect(self) -> list:
        client = self._make_client("elbv2")
        resources = []

        self.logger.info("Collecting Elastic Load Balancers")

        try:
            paginator = client.get_paginator("describe_load_balancers")

            for page in paginator.paginate():
                lbs = page.get("LoadBalancers", [])
                arns = [lb.get("LoadBalancerArn") for lb in lbs if lb.get("LoadBalancerArn")]
                tags_by_arn = self._fetch_tags_for_arns(client, arns)

                for lb in lbs:
                    arn = lb.get("LoadBalancerArn")
                    name = lb.get("LoadBalancerName") or arn
                    lb_type = lb.get("Type", "application")
                    state = lb.get("State", {}).get("Code", "unknown")
                    created_at = lb.get("CreatedTime")
                    tags = tags_by_arn.get(arn, {})

                    tags.update(
                        {
                            "_lb_type": lb_type,
                            "_scheme": lb.get("Scheme", "unknown"),
                            "_vpc_id": lb.get("VpcId", ""),
                            "_ip_type": lb.get("IpAddressType", ""),
                        }
                    )

                    resources.append(
                        {
                            "resource_id": arn,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": name,
                            "account_id": self.account_id,
                            "region": self.region,
                            "state": state,
                            "created_at": created_at,
                            "tags": tags,
                            "estimated_cost_usd": estimate_load_balancer_cost(
                                lb_type, created_at
                            ),
                            "raw_api_response": lb,
                        }
                    )

        except Exception as e:
            self.logger.error(f"Load balancer collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} load balancer(s)")
        return resources

    def _fetch_tags_for_arns(self, client, arns: list) -> dict:
        tags_by_arn = {}
        if not arns:
            return tags_by_arn

        # ELBv2 DescribeTags accepts up to 20 ARNs per request.
        for i in range(0, len(arns), 20):
            batch = arns[i : i + 20]
            try:
                response = client.describe_tags(ResourceArns=batch)
                for desc in response.get("TagDescriptions", []):
                    arn = desc.get("ResourceArn")
                    tags_by_arn[arn] = self._extract_tags(desc.get("Tags", []))
            except Exception as e:
                self.logger.warning(f"Could not fetch ELB tags for batch: {e}")

        return tags_by_arn
