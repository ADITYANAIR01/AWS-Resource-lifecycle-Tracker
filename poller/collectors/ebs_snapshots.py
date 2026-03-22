"""
EBS snapshots collector.

Collects EBS snapshots owned by this account only.
Without OwnerIds filter, AWS returns every public snapshot
in the region — potentially millions of rows.

States tracked: completed, pending, error
Skips: none — all owned snapshots are tracked
"""

from collectors.base import BaseCollector
from utils.cost import estimate_ebs_snapshot_cost


class EBSSnapshotCollector(BaseCollector):

    RESOURCE_TYPE = "ebs_snapshot"

    def collect(self) -> list:
        client    = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting EBS snapshots")

        try:
            paginator = client.get_paginator("describe_snapshots")

            # OwnerIds=['self'] is critical — without it AWS returns
            # every public snapshot in the region
            for page in paginator.paginate(OwnerIds=["self"]):
                for snapshot in page.get("Snapshots", []):

                    resource_id = snapshot["SnapshotId"]
                    tags_raw    = snapshot.get("Tags", [])
                    tags        = self._extract_tags(tags_raw)
                    name        = self._extract_name(tags_raw, resource_id)
                    state       = snapshot.get("State", "unknown")
                    start_time  = snapshot.get("StartTime")
                    size_gb     = snapshot.get("VolumeSize", 0)
                    cost        = estimate_ebs_snapshot_cost(size_gb, start_time)

                    resources.append({
                        "resource_id":        resource_id,
                        "resource_type":      self.RESOURCE_TYPE,
                        "resource_name":      name,
                        "account_id":         self.account_id,
                        "region":             self.region,
                        "state":              state,
                        "created_at":         start_time,
                        "tags":               tags,
                        "estimated_cost_usd": cost,
                        "raw_api_response":   snapshot,
                    })

        except Exception as e:
            self.logger.error(f"EBS snapshot collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} EBS snapshot(s)")
        return resources