"""
Elastic IPs collector.

Collects all Elastic IPs in the configured region.
State: 'associated' if attached to a resource, 'unassociated' if not.

Unassociated EIPs cost $0.005/hr — AWS charges even when unused.
These are flagged as critical alerts.

Note: Elastic IPs have no creation timestamp in the AWS API.
created_at is stored as None.
"""

from collectors.base import BaseCollector
from utils.cost import estimate_elastic_ip_cost


class ElasticIPCollector(BaseCollector):

    RESOURCE_TYPE = "elastic_ip"

    def collect(self) -> list:
        client    = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting Elastic IPs")

        try:
            response = client.describe_addresses()

            for address in response.get("Addresses", []):

                allocation_id = address.get("AllocationId", address.get("PublicIp"))
                public_ip     = address.get("PublicIp", allocation_id)
                tags_raw      = address.get("Tags", [])
                tags          = self._extract_tags(tags_raw)
                name          = self._extract_name(tags_raw, public_ip)

                # State based on whether associated with any resource
                is_associated = "AssociationId" in address
                state         = "associated" if is_associated else "unassociated"

                # Only unassociated EIPs incur cost
                cost = estimate_elastic_ip_cost() if not is_associated else 0

                resources.append({
                    "resource_id":        allocation_id,
                    "resource_type":      self.RESOURCE_TYPE,
                    "resource_name":      name,
                    "account_id":         self.account_id,
                    "region":             self.region,
                    "state":              state,
                    "created_at":         None,
                    "tags":               tags,
                    "estimated_cost_usd": cost,
                    "raw_api_response":   address,
                })

        except Exception as e:
            self.logger.error(f"Elastic IP collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} Elastic IP(s)")
        return resources