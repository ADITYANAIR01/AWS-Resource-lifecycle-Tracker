"""
EBS volumes collector.

Collects all EBS volumes in the configured region.
Skips 'deleted' and 'deleting' volumes.

Key states tracked:
  in-use    -> attached to an EC2 instance (normal)
  available -> unattached — potentially forgotten, still billed
  error     -> worth alerting on
"""

from collectors.base import BaseCollector
from utils.cost import estimate_ebs_volume_cost


class EBSVolumeCollector(BaseCollector):

    RESOURCE_TYPE = "ebs_volume"

    _SKIP_STATES = {"deleted", "deleting"}

    def collect(self) -> list:
        """
        Collect all active EBS volumes via describe_volumes paginator.
        """
        client    = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting EBS volumes")

        try:
            paginator = client.get_paginator("describe_volumes")

            for page in paginator.paginate():
                for volume in page.get("Volumes", []):

                    state = volume.get("State", "unknown")

                    if state in self._SKIP_STATES:
                        continue

                    resource_id = volume["VolumeId"]
                    tags_raw    = volume.get("Tags", [])
                    tags        = self._extract_tags(tags_raw)
                    name        = self._extract_name(tags_raw, resource_id)
                    size_gb     = volume.get("Size", 0)
                    volume_type = volume.get("VolumeType", "gp2")
                    create_time = volume.get("CreateTime")
                    cost        = estimate_ebs_volume_cost(size_gb, volume_type, create_time)

                    resources.append({
                        "resource_id":        resource_id,
                        "resource_type":      self.RESOURCE_TYPE,
                        "resource_name":      name,
                        "account_id":         self.account_id,
                        "region":             self.region,
                        "state":              state,
                        "created_at":         create_time,
                        "tags":               tags,
                        "estimated_cost_usd": cost,
                        "raw_api_response":   volume,
                    })

        except Exception as e:
            self.logger.error(f"EBS volume collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} EBS volume(s)")
        return resources