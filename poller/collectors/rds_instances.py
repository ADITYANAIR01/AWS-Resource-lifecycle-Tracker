"""
RDS instances collector.

Collects all RDS DB instances in the configured region.
Skips 'deleted' instances.

Tags are NOT included in describe_db_instances — requires a separate
list_tags_for_resource call per instance using the DBInstanceArn.
If the tags call fails for one instance, we store empty tags and continue.
"""

from collectors.base import BaseCollector
from utils.cost import estimate_rds_cost


class RDSInstanceCollector(BaseCollector):

    RESOURCE_TYPE = "rds"

    _SKIP_STATES = {"deleted", "deleting"}

    def collect(self) -> list:
        client    = self._make_client("rds")
        resources = []

        self.logger.info("Collecting RDS instances")

        try:
            paginator = client.get_paginator("describe_db_instances")

            for page in paginator.paginate():
                for instance in page.get("DBInstances", []):

                    state = instance.get("DBInstanceStatus", "unknown")

                    if state in self._SKIP_STATES:
                        continue

                    resource_id  = instance["DBInstanceIdentifier"]
                    instance_arn = instance.get("DBInstanceArn", "")
                    db_class     = instance.get("DBInstanceClass", "unknown")
                    create_time  = instance.get("InstanceCreateTime")
                    cost         = estimate_rds_cost(db_class, create_time)

                    # Tags require a separate API call for RDS
                    tags = self._fetch_rds_tags(client, instance_arn)

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
                        "raw_api_response":   instance,
                    })

        except Exception as e:
            self.logger.error(f"RDS instance collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} RDS instance(s)")
        return resources

    def _fetch_rds_tags(self, client, resource_arn: str) -> dict:
        """
        Fetch tags for an RDS resource via list_tags_for_resource.
        Returns empty dict if call fails — never crashes the collector.
        """
        if not resource_arn:
            return {}
        try:
            response = client.list_tags_for_resource(ResourceName=resource_arn)
            return self._extract_tags(response.get("TagList", []))
        except Exception as e:
            self.logger.warning(
                f"Could not fetch tags for RDS resource {resource_arn}: {e}"
            )
            return {}