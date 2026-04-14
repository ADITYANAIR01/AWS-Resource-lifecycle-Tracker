"""
EKS clusters collector.

Collects EKS clusters and nodegroup metadata in the configured region.
Resource granularity is one row per cluster (resource_type='eks').

Internal metadata stored in tags for alerting/analytics:
  - _version
  - _endpoint
  - _nodegroup_count
  - _desired_nodes_total
"""

from datetime import timezone
from decimal import Decimal

from collectors.base import BaseCollector
from utils.cost import estimate_eks_cluster_cost, estimate_eks_nodegroup_cost


class EKSCollector(BaseCollector):

    RESOURCE_TYPE = "eks"

    def collect(self) -> list:
        eks = self._make_client("eks")
        resources = []

        self.logger.info("Collecting EKS clusters")

        try:
            cluster_names = self._list_cluster_names(eks)

            for cluster_name in cluster_names:
                cluster_resp = eks.describe_cluster(name=cluster_name)
                cluster = cluster_resp.get("cluster", {})

                cluster_arn = cluster.get("arn") or cluster_name
                cluster_state = (cluster.get("status") or "UNKNOWN").upper()
                created_at = self._ensure_utc(cluster.get("createdAt"))
                version = cluster.get("version", "unknown")
                endpoint = cluster.get("endpoint", "")

                tags = dict(cluster.get("tags") or {})
                tags.update(self._fetch_cluster_tags(eks, cluster_arn))

                nodegroups = self._collect_nodegroups(eks, cluster_name, created_at)
                nodegroup_cost = nodegroups["cost"]
                nodegroup_items = nodegroups["items"]
                desired_nodes_total = nodegroups["desired_total"]

                tags.update(
                    {
                        "_version": str(version),
                        "_endpoint": endpoint,
                        "_nodegroup_count": str(len(nodegroup_items)),
                        "_desired_nodes_total": str(desired_nodes_total),
                    }
                )

                total_cost = estimate_eks_cluster_cost(created_at) + nodegroup_cost

                resources.append(
                    {
                        "resource_id": cluster_arn,
                        "resource_type": self.RESOURCE_TYPE,
                        "resource_name": cluster_name,
                        "account_id": self.account_id,
                        "region": self.region,
                        "state": cluster_state,
                        "created_at": created_at,
                        "tags": tags,
                        "estimated_cost_usd": round(total_cost, 4),
                        "raw_api_response": {
                            "cluster": cluster,
                            "nodegroups": nodegroup_items,
                        },
                    }
                )

        except Exception as e:
            self.logger.error(f"EKS collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} EKS cluster(s)")
        return resources

    def _list_cluster_names(self, eks) -> list:
        names = []
        paginator = eks.get_paginator("list_clusters")
        for page in paginator.paginate():
            names.extend(page.get("clusters", []))
        return names

    def _list_nodegroup_names(self, eks, cluster_name: str) -> list:
        names = []
        paginator = eks.get_paginator("list_nodegroups")
        for page in paginator.paginate(clusterName=cluster_name):
            names.extend(page.get("nodegroups", []))
        return names

    def _collect_nodegroups(self, eks, cluster_name: str, cluster_created_at):
        items = []
        total_cost = Decimal("0")
        desired_total = 0

        for nodegroup_name in self._list_nodegroup_names(eks, cluster_name):
            try:
                response = eks.describe_nodegroup(
                    clusterName=cluster_name,
                    nodegroupName=nodegroup_name,
                )
                nodegroup = response.get("nodegroup", {})

                scaling = nodegroup.get("scalingConfig", {})
                desired_size = int(scaling.get("desiredSize") or 0)
                instance_types = nodegroup.get("instanceTypes", [])
                primary_instance_type = instance_types[0] if instance_types else ""
                node_created_at = self._ensure_utc(
                    nodegroup.get("createdAt") or cluster_created_at
                )

                desired_total += desired_size
                total_cost += estimate_eks_nodegroup_cost(
                    primary_instance_type,
                    desired_size,
                    node_created_at,
                )

                items.append(
                    {
                        "nodegroup_name": nodegroup_name,
                        "status": (nodegroup.get("status") or "UNKNOWN").upper(),
                        "instance_types": instance_types,
                        "desired_size": desired_size,
                        "min_size": int(scaling.get("minSize") or 0),
                        "max_size": int(scaling.get("maxSize") or 0),
                        "created_at": (
                            node_created_at.isoformat() if node_created_at else None
                        ),
                    }
                )

            except Exception as e:
                self.logger.warning(
                    f"Could not collect EKS nodegroup {cluster_name}/{nodegroup_name}: {e}"
                )

        return {
            "items": items,
            "cost": round(total_cost, 4),
            "desired_total": desired_total,
        }

    def _fetch_cluster_tags(self, eks, cluster_arn: str) -> dict:
        if not cluster_arn:
            return {}

        try:
            response = eks.list_tags_for_resource(resourceArn=cluster_arn)
            return response.get("tags", {}) or {}
        except Exception as e:
            self.logger.warning(f"Could not fetch tags for EKS cluster {cluster_arn}: {e}")
            return {}

    def _ensure_utc(self, dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
