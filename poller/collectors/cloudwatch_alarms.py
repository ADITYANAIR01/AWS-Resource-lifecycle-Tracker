"""
CloudWatch alarms collector.

Collects all CloudWatch alarms in the configured region.
State comes directly from the API: OK, ALARM, INSUFFICIENT_DATA.

Alarms stuck in INSUFFICIENT_DATA for 7+ days are likely orphaned —
the metric they were monitoring no longer exists. These are flagged
by the alert engine in Phase 5.

created_at = AlarmConfigurationUpdatedTimestamp (last config change).
There is no original creation timestamp in the CloudWatch API.
"""

from collectors.base import BaseCollector


class CloudWatchAlarmCollector(BaseCollector):

    RESOURCE_TYPE = "cloudwatch_alarm"

    def collect(self) -> list:
        client    = self._make_client("cloudwatch")
        resources = []

        self.logger.info("Collecting CloudWatch alarms")

        try:
            paginator = client.get_paginator("describe_alarms")

            for page in paginator.paginate(AlarmTypes=["MetricAlarm"]):
                for alarm in page.get("MetricAlarms", []):

                    alarm_name = alarm["AlarmName"]
                    alarm_arn  = alarm.get("AlarmArn", "")
                    state      = alarm.get("StateValue", "unknown")
                    updated_at = alarm.get("AlarmConfigurationUpdatedTimestamp")
                    tags_raw   = self._fetch_alarm_tags(client, alarm_arn)
                    tags       = self._extract_tags(tags_raw)

                    resources.append({
                        "resource_id":        alarm_arn or alarm_name,
                        "resource_type":      self.RESOURCE_TYPE,
                        "resource_name":      alarm_name,
                        "account_id":         self.account_id,
                        "region":             self.region,
                        "state":              state,
                        "created_at":         updated_at,
                        "tags":               tags,
                        "estimated_cost_usd": 0,
                        "raw_api_response":   alarm,
                    })

        except Exception as e:
            self.logger.error(f"CloudWatch alarm collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} CloudWatch alarm(s)")
        return resources

    def _fetch_alarm_tags(self, client, alarm_arn: str) -> list:
        """
        Fetch tags for a CloudWatch alarm.
        Returns [] on failure — never crashes the collector.
        """
        if not alarm_arn:
            return []
        try:
            response = client.list_tags_for_resource(ResourceARN=alarm_arn)
            return response.get("Tags", [])
        except Exception as e:
            self.logger.warning(
                f"Could not fetch tags for alarm {alarm_arn}: {e}"
            )
            return []