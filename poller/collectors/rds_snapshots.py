"""
RDS snapshots collector.

Collects manual RDS snapshots only.
Automated snapshots are AWS-managed and rotate themselves —
tracking them adds noise with no portfolio value.

States tracked: available, creating, copying, error
Skips: deleted, deleting
"""

from collectors.base import BaseCollector
from utils.cost import estimate_ebs_snapshot_cost


class RDSSnapshotCollector(BaseCollector):

    RESOURCE_TYPE = "rds_snapshot"

    _SKIP_STATES = {"deleted", "deleting"}

    def collect(self) -> list:
        client    = self._make_client("rds")
        resources = []

        self.logger.info("Collecting RDS snapshots (manual only)")

        try:
            paginator = client.get_paginator("describe_db_snapshots")

            # SnapshotType='manual' — skip automated snapshots
            for page in paginator.paginate(SnapshotType="manual"):
                for snapshot in page.get("DBSnapshots", []):

                    state = snapshot.get("Status", "unknown")

                    if state in self._SKIP_STATES:
                        continue

                    resource_id   = snapshot["DBSnapshotIdentifier"]
                    snapshot_arn  = snapshot.get("DBSnapshotArn", "")
                    create_time   = snapshot.get("SnapshotCreateTime")
                    size_gb       = snapshot.get("AllocatedStorage", 0)
                    cost          = estimate_ebs_snapshot_cost(size_gb, create_time)

                    tags = self._fetch_rds_tags(client, snapshot_arn)

                    resources.append({
                        "resource_id":        resource_id,
                        "resource_type":      self.RESOURCE_TYPE,
                        "resource_name":      resource_id,
                        "account_id":         self.account_id,
                        "region":             self.region,
                        "state":              state,
                        "created_at":         create_time,
                        "tags":               tags,
                        "estimated_cost_usd": cost,
                        "raw_api_response":   snapshot,
                    })

        except Exception as e:
            self.logger.error(f"RDS snapshot collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} RDS snapshot(s)")
        return resources

    def _fetch_rds_tags(self, client, resource_arn: str) -> dict:
        if not resource_arn:
            return {}
        try:
            response = client.list_tags_for_resource(ResourceName=resource_arn)
            return self._extract_tags(response.get("TagList", []))
        except Exception as e:
            self.logger.warning(
                f"Could not fetch tags for RDS snapshot {resource_arn}: {e}"
            )
            return {}