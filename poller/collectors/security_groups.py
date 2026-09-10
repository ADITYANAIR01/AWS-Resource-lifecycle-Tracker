"""
Security groups collector.

Collects all security groups in the configured region.
State: 'in-use' if attached to any network interface, 'unused' if not.

Unused security groups are clutter — they accumulate over time
and make environments harder to audit.

Strategy:
  1. Call describe_network_interfaces to build a set of all
     SG IDs currently attached to something.
  2. Mark each SG as in-use or unused based on that set.
  3. The default SG (named 'default') cannot be deleted by AWS —
     we track it but never flag it as a problem.

Security groups have no creation timestamp in the AWS API.
created_at is stored as None.
"""

from collectors.base import BaseCollector


class SecurityGroupCollector(BaseCollector):

    RESOURCE_TYPE = "security_group"

    def collect(self) -> list:
        client = self._make_client("ec2")
        resources = []

        self.logger.info("Collecting Security Groups")

        try:
            # Step 1 — Build set of all SG IDs currently in use.
            # Fail-CLOSED: _get_in_use_sg_ids returns None when the ENI
            # lookup fails, and we raise so the poller records this
            # collector in the partial_failure path instead of marking
            # every SG "unused" (which would spam security_group_unused
            # alerts). See _get_in_use_sg_ids docstring.
            in_use_sg_ids = self._get_in_use_sg_ids(client)
            if in_use_sg_ids is None:
                raise RuntimeError(
                    "ENI lookup failed — cannot determine SG attachment; "
                    "aborting SG collection (fail-closed)"
                )
            self.logger.info(
                f"Found {len(in_use_sg_ids)} security group(s) currently in use"
            )

            # Step 2 — Collect all security groups
            paginator = client.get_paginator("describe_security_groups")

            for page in paginator.paginate():
                for sg in page.get("SecurityGroups", []):

                    sg_id = sg["GroupId"]
                    sg_name = sg.get("GroupName", sg_id)
                    tags_raw = sg.get("Tags", [])
                    tags = self._extract_tags(tags_raw)
                    name = self._extract_name(tags_raw, sg_name)

                    # Default SG cannot be deleted — mark as in-use always
                    if sg_name == "default":
                        state = "in-use"
                    else:
                        state = "in-use" if sg_id in in_use_sg_ids else "unused"

                    resources.append(
                        {
                            "resource_id": sg_id,
                            "resource_type": self.RESOURCE_TYPE,
                            "resource_name": name,
                            "account_id": self.account_id,
                            "region": self.region,
                            "state": state,
                            "created_at": None,
                            "tags": tags,
                            "estimated_cost_usd": 0,
                            "raw_api_response": sg,
                        }
                    )

        except Exception as e:
            self.logger.error(f"Security group collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} security group(s)")
        return resources

    def _get_in_use_sg_ids(self, client) -> set | None:
        """
        Return a set of SG IDs that are currently attached to
        at least one network interface.

        Returns None (sentinel) when the ENI lookup fails, so the
        caller can fail CLOSED by raising into the poller's
        partial_failure path. Never return an empty set on failure:
        an empty set would mark every non-default SG "unused" and
        trigger bogus security_group_unused alerts (fail-open bug).
        A genuinely empty result (account with no ENIs) still
        returns an empty set — only exceptions yield None.
        """
        in_use = set()
        try:
            paginator = client.get_paginator("describe_network_interfaces")
            for page in paginator.paginate():
                for eni in page.get("NetworkInterfaces", []):
                    for group in eni.get("Groups", []):
                        gid = group.get("GroupId")
                        if gid:
                            in_use.add(gid)
        except Exception as e:
            self.logger.warning(
                f"Could not fetch network interfaces for SG in-use check: {e}. "
                f"Fail-closed: returning None so collection aborts instead of "
                f"marking all SGs unused."
            )
            return None
        return in_use
