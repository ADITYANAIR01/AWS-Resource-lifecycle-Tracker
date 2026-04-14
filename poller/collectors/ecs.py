"""
ECS services collector.

Collects ECS clusters and services, including task definition details
and running task health metadata.

Resource granularity:
  - One resource row per ECS service (resource_type='ecs')

Internal metadata stored in tags for alert queries:
  - _cluster_name
  - _service_name
  - _launch_type
  - _desired_count
  - _running_count
  - _task_definition_family
"""

from datetime import timezone
from decimal import Decimal

from collectors.base import BaseCollector
from utils.cost import estimate_ec2_cost, estimate_fargate_task_cost


class ECSCollector(BaseCollector):

    RESOURCE_TYPE = "ecs"

    _CLUSTER_BATCH_SIZE = 100
    _SERVICE_BATCH_SIZE = 10
    _TASK_BATCH_SIZE = 100
    _CONTAINER_INSTANCE_BATCH_SIZE = 100
    _EC2_INSTANCE_BATCH_SIZE = 100

    def collect(self) -> list:
        ecs = self._make_client("ecs")
        resources = []
        task_def_cache = {}

        self.logger.info("Collecting ECS services")

        try:
            cluster_arns = self._list_cluster_arns(ecs)
            if not cluster_arns:
                self.logger.info("Collected 0 ECS service(s)")
                return []

            for cluster_batch in self._chunked(cluster_arns, self._CLUSTER_BATCH_SIZE):
                response = ecs.describe_clusters(clusters=cluster_batch, include=["TAGS"])

                for cluster in response.get("clusters", []):
                    cluster_arn = cluster.get("clusterArn")
                    cluster_name = cluster.get("clusterName") or self._short_name(
                        cluster_arn, "cluster"
                    )
                    cluster_state = (cluster.get("status") or "INACTIVE").upper()
                    cluster_tags = self._extract_tags(cluster.get("tags", []))
                    cluster_tags.update(self._fetch_resource_tags(ecs, cluster_arn))

                    service_arns = self._list_service_arns(ecs, cluster_arn)
                    if not service_arns:
                        continue

                    for service_batch in self._chunked(
                        service_arns, self._SERVICE_BATCH_SIZE
                    ):
                        service_resp = ecs.describe_services(
                            cluster=cluster_arn,
                            services=service_batch,
                            include=["TAGS"],
                        )

                        for service in service_resp.get("services", []):
                            resource = self._build_service_resource(
                                ecs,
                                service,
                                cluster_arn,
                                cluster_name,
                                cluster_state,
                                cluster_tags,
                                task_def_cache,
                            )
                            if resource is not None:
                                resources.append(resource)

        except Exception as e:
            self.logger.error(f"ECS collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} ECS service(s)")
        return resources

    def _build_service_resource(
        self,
        ecs,
        service: dict,
        cluster_arn: str,
        cluster_name: str,
        cluster_state: str,
        cluster_tags: dict,
        task_def_cache: dict,
    ) -> dict:
        service_arn = service.get("serviceArn")
        service_name = service.get("serviceName") or self._short_name(service_arn, "service")
        service_status = (service.get("status") or "ACTIVE").upper()

        desired_count = int(service.get("desiredCount") or 0)
        running_count = int(service.get("runningCount") or 0)
        launch_type = self._detect_launch_type(service)

        created_at = self._ensure_utc(service.get("createdAt"))
        task_definition_arn = service.get("taskDefinition", "")
        task_definition = self._get_task_definition(ecs, task_definition_arn, task_def_cache)
        task_family = task_definition.get("family") or "unknown"
        task_cpu, task_memory = self._extract_task_size(task_definition)

        running_task_arns = self._list_running_tasks(ecs, cluster_arn, service_name)
        state = self._derive_state(service_status, desired_count, running_count)

        # Service tags + cluster tags + alert metadata.
        tags = dict(cluster_tags)
        tags.update(self._extract_tags(service.get("tags", [])))
        tags.update(self._fetch_resource_tags(ecs, service_arn))
        tags.update(
            {
                "_cluster_name": cluster_name,
                "_service_name": service_name,
                "_launch_type": launch_type,
                "_desired_count": str(desired_count),
                "_running_count": str(running_count),
                "_task_definition_family": task_family,
            }
        )

        if launch_type == "FARGATE":
            estimated_cost = estimate_fargate_task_cost(
                cpu_units=task_cpu,
                memory_mib=task_memory,
                start_time=created_at,
                task_count=max(running_count, 1),
            )
        else:
            estimated_cost = self._estimate_ec2_backing_cost(
                ecs,
                cluster_arn,
                running_task_arns,
            )

        raw = {
            "cluster": {
                "clusterArn": cluster_arn,
                "clusterName": cluster_name,
                "status": cluster_state,
            },
            "service": service,
            "task_definition": {
                "taskDefinitionArn": task_definition_arn,
                "family": task_family,
                "cpu": str(task_cpu),
                "memory": str(task_memory),
            },
            "running_task_arns": running_task_arns,
        }

        return {
            "resource_id": service_arn or f"{cluster_name}/{service_name}",
            "resource_type": self.RESOURCE_TYPE,
            "resource_name": f"{cluster_name}/{service_name}",
            "account_id": self.account_id,
            "region": self.region,
            "state": state,
            "created_at": created_at,
            "tags": tags,
            "estimated_cost_usd": estimated_cost,
            "raw_api_response": raw,
        }

    def _list_cluster_arns(self, ecs) -> list:
        arns = []
        paginator = ecs.get_paginator("list_clusters")
        for page in paginator.paginate():
            arns.extend(page.get("clusterArns", []))
        return arns

    def _list_service_arns(self, ecs, cluster_arn: str) -> list:
        try:
            arns = []
            paginator = ecs.get_paginator("list_services")
            for page in paginator.paginate(cluster=cluster_arn):
                arns.extend(page.get("serviceArns", []))
            return arns
        except Exception as e:
            self.logger.warning(
                f"Could not list ECS services for cluster {cluster_arn}: {e}"
            )
            return []

    def _list_running_tasks(self, ecs, cluster_arn: str, service_name: str) -> list:
        try:
            arns = []
            paginator = ecs.get_paginator("list_tasks")
            for page in paginator.paginate(
                cluster=cluster_arn,
                serviceName=service_name,
                desiredStatus="RUNNING",
            ):
                arns.extend(page.get("taskArns", []))
            return arns
        except Exception as e:
            self.logger.warning(
                f"Could not list running ECS tasks for {service_name}: {e}"
            )
            return []

    def _fetch_resource_tags(self, ecs, resource_arn: str) -> dict:
        if not resource_arn:
            return {}
        try:
            response = ecs.list_tags_for_resource(resourceArn=resource_arn)
            return self._extract_tags(response.get("tags", []))
        except Exception as e:
            self.logger.warning(f"Could not fetch ECS tags for {resource_arn}: {e}")
            return {}

    def _get_task_definition(self, ecs, task_definition_arn: str, cache: dict) -> dict:
        if not task_definition_arn:
            return {}

        if task_definition_arn in cache:
            return cache[task_definition_arn]

        try:
            response = ecs.describe_task_definition(taskDefinition=task_definition_arn)
            task_definition = response.get("taskDefinition", {})
            cache[task_definition_arn] = task_definition
            return task_definition
        except Exception as e:
            self.logger.warning(
                f"Could not describe task definition {task_definition_arn}: {e}"
            )
            cache[task_definition_arn] = {}
            return {}

    def _extract_task_size(self, task_definition: dict) -> tuple:
        cpu_raw = task_definition.get("cpu")
        mem_raw = task_definition.get("memory")

        cpu_units = int(cpu_raw) if str(cpu_raw or "").isdigit() else 0
        memory_mib = int(mem_raw) if str(mem_raw or "").isdigit() else 0

        # If task-level sizing is not present, sum from container definitions.
        if cpu_units <= 0 or memory_mib <= 0:
            cpu_sum = 0
            mem_sum = 0
            for c in task_definition.get("containerDefinitions", []):
                cpu = c.get("cpu")
                mem = c.get("memory") or c.get("memoryReservation")
                cpu_sum += int(cpu) if str(cpu or "").isdigit() else 0
                mem_sum += int(mem) if str(mem or "").isdigit() else 0

            if cpu_units <= 0:
                cpu_units = cpu_sum
            if memory_mib <= 0:
                memory_mib = mem_sum

        return cpu_units, memory_mib

    def _estimate_ec2_backing_cost(self, ecs, cluster_arn: str, task_arns: list) -> Decimal:
        if not task_arns:
            return Decimal("0")

        try:
            service_tasks_per_container_instance = {}

            for task_batch in self._chunked(task_arns, self._TASK_BATCH_SIZE):
                task_resp = ecs.describe_tasks(cluster=cluster_arn, tasks=task_batch)
                for task in task_resp.get("tasks", []):
                    container_instance_arn = task.get("containerInstanceArn")
                    if container_instance_arn:
                        service_tasks_per_container_instance[container_instance_arn] = (
                            service_tasks_per_container_instance.get(
                                container_instance_arn, 0
                            )
                            + 1
                        )

            container_instance_arns = set(service_tasks_per_container_instance.keys())

            if not container_instance_arns:
                return Decimal("0")

            container_instance_details = {}
            ec2_ids = set()
            container_arn_list = list(container_instance_arns)
            for ci_batch in self._chunked(
                container_arn_list, self._CONTAINER_INSTANCE_BATCH_SIZE
            ):
                ci_resp = ecs.describe_container_instances(
                    cluster=cluster_arn,
                    containerInstances=ci_batch,
                )
                for ci in ci_resp.get("containerInstances", []):
                    container_instance_arn = ci.get("containerInstanceArn")
                    ec2_instance_id = ci.get("ec2InstanceId")
                    running_tasks_count = int(ci.get("runningTasksCount") or 0)
                    if ec2_instance_id:
                        ec2_ids.add(ec2_instance_id)
                        container_instance_details[container_instance_arn] = {
                            "ec2_instance_id": ec2_instance_id,
                            "running_tasks_count": running_tasks_count,
                        }

            if not ec2_ids:
                return Decimal("0")

            ec2 = self._make_client("ec2")
            ec2_cost_by_id = {}

            ec2_id_list = list(ec2_ids)
            for id_batch in self._chunked(ec2_id_list, self._EC2_INSTANCE_BATCH_SIZE):
                response = ec2.describe_instances(InstanceIds=id_batch)
                for reservation in response.get("Reservations", []):
                    for instance in reservation.get("Instances", []):
                        instance_id = instance.get("InstanceId")
                        instance_type = instance.get("InstanceType", "")
                        launch_time = self._ensure_utc(instance.get("LaunchTime"))
                        ec2_cost_by_id[instance_id] = estimate_ec2_cost(
                            instance_type, launch_time
                        )

            total = Decimal("0")
            for container_instance_arn, service_task_count in (
                service_tasks_per_container_instance.items()
            ):
                details = container_instance_details.get(container_instance_arn)
                if not details:
                    continue

                ec2_instance_id = details.get("ec2_instance_id")
                ec2_instance_cost = ec2_cost_by_id.get(ec2_instance_id, Decimal("0"))
                if ec2_instance_cost <= 0:
                    continue

                # Share host cost by this service's running-task fraction
                # on the container instance to reduce cross-service double-counting.
                running_tasks_count = details.get("running_tasks_count", 0)
                denominator = max(running_tasks_count, service_task_count, 1)
                share = Decimal(str(service_task_count)) / Decimal(str(denominator))
                total += ec2_instance_cost * share

            return round(total, 4)

        except Exception as e:
            self.logger.warning(
                f"Could not estimate ECS EC2 backing cost for {cluster_arn}: {e}"
            )
            return Decimal("0")

    def _derive_state(self, service_status: str, desired_count: int, running_count: int) -> str:
        if service_status in {"INACTIVE", "DRAINING"}:
            return "INACTIVE"
        if desired_count > 0 and running_count < desired_count:
            return "FAILED"
        if desired_count == 0 and running_count == 0:
            return "INACTIVE"
        if running_count > 0:
            return "ACTIVE"
        return "PENDING"

    def _detect_launch_type(self, service: dict) -> str:
        launch_type = (service.get("launchType") or "").upper()
        if launch_type:
            return launch_type

        for cp in service.get("capacityProviderStrategy", []):
            provider = (cp.get("capacityProvider") or "").upper()
            if "FARGATE" in provider:
                return "FARGATE"

        return "EC2"

    def _ensure_utc(self, dt):
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _short_name(self, arn: str, fallback: str) -> str:
        if not arn:
            return fallback
        return arn.split("/")[-1]

    def _chunked(self, items: list, size: int):
        for i in range(0, len(items), size):
            yield items[i : i + size]
