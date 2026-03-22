"""
EC2 instances collector.

Collects all EC2 instances in the configured region.
Skips 'terminated' and 'shutting-down' instances — they no longer exist
and billing has stopped. Running and stopped instances are both tracked.
"""

from collectors.base import BaseCollector
from utils.cost import estimate_ec2_cost


class EC2Collector(BaseCollector):

    RESOURCE_TYPE = "ec2"

    _SKIP_STATES = {"terminated", "shutting-down"}

    def collect(self) -> list:
        """
        Collect all non-terminated EC2 instances.
        AWS returns instances grouped in Reservations — we flatten this
        into a single list of resource dicts.
        """
        client    = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting EC2 instances")

        try:
            paginator = client.get_paginator("describe_instances")

            for page in paginator.paginate():
                for reservation in page.get("Reservations", []):
                    for instance in reservation.get("Instances", []):

                        state = instance.get("State", {}).get("Name", "unknown")

                        if state in self._SKIP_STATES:
                            continue

                        resource_id   = instance["InstanceId"]
                        tags_raw      = instance.get("Tags", [])
                        tags          = self._extract_tags(tags_raw)
                        name          = self._extract_name(tags_raw, resource_id)
                        instance_type = instance.get("InstanceType", "unknown")
                        launch_time   = instance.get("LaunchTime")
                        cost          = estimate_ec2_cost(instance_type, launch_time)

                        resources.append({
                            "resource_id":        resource_id,
                            "resource_type":      self.RESOURCE_TYPE,
                            "resource_name":      name,
                            "account_id":         self.account_id,
                            "region":             self.region,
                            "state":              state,
                            "created_at":         launch_time,
                            "tags":               tags,
                            "estimated_cost_usd": cost,
                            "raw_api_response":   instance,
                        })

        except Exception as e:
            self.logger.error(f"EC2 collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} EC2 instance(s)")
        return resources