"""
S3 buckets collector.

S3 is a global service — list_buckets returns all buckets
regardless of region. We call get_bucket_location per bucket
to store the actual region each bucket lives in.

get_bucket_tagging raises NoSuchTagSet when a bucket has no tags.
This is expected — we catch it specifically and return empty tags.

Cost estimation not available in v1 — requires Storage Lens or
CloudWatch metrics. Displayed as N/A in dashboard.
"""

from collectors.base import BaseCollector


class S3Collector(BaseCollector):

    RESOURCE_TYPE = "s3"

    def collect(self) -> list:
        # S3 is global — no region needed for list_buckets
        client    = self._make_client("s3")
        resources = []

        self.logger.info("Collecting S3 buckets")

        try:
            response = client.list_buckets()

            for bucket in response.get("Buckets", []):
                name        = bucket["Name"]
                create_time = bucket.get("CreationDate")

                # Get actual bucket region
                bucket_region = self._get_bucket_region(client, name)

                # Get tags — NoSuchTagSet is expected for untagged buckets
                tags = self._get_bucket_tags(client, name)

                resources.append({
                    "resource_id":        name,
                    "resource_type":      self.RESOURCE_TYPE,
                    "resource_name":      name,
                    "account_id":         self.account_id,
                    "region":             bucket_region,
                    "state":              "active",
                    "created_at":         create_time,
                    "tags":               tags,
                    "estimated_cost_usd": 0,
                    "raw_api_response":   bucket,
                })

        except Exception as e:
            self.logger.error(f"S3 collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} S3 bucket(s)")
        return resources

    def _get_bucket_region(self, client, bucket_name: str) -> str:
        """
        Get the region a bucket lives in.
        Returns None for us-east-1 — AWS returns None for the default region.
        We normalise this to 'us-east-1' explicitly.
        """
        try:
            response = client.get_bucket_location(Bucket=bucket_name)
            location = response.get("LocationConstraint")
            # AWS returns None for us-east-1 (legacy behaviour)
            return location if location else "us-east-1"
        except Exception as e:
            self.logger.warning(
                f"Could not get region for bucket {bucket_name}: {e}"
            )
            return "unknown"

    def _get_bucket_tags(self, client, bucket_name: str) -> dict:
        """
        Get bucket tags. NoSuchTagSet is expected when a bucket has no tags
        and is not an error — return empty dict silently.
        """
        try:
            response = client.get_bucket_tagging(Bucket=bucket_name)
            return self._extract_tags(response.get("TagSet", []))
        except client.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NoSuchTagSet":
                # Expected — bucket has no tags
                return {}
            self.logger.warning(
                f"Could not get tags for bucket {bucket_name}: {e}"
            )
            return {}
        except Exception as e:
            self.logger.warning(
                f"Could not get tags for bucket {bucket_name}: {e}"
            )
            return {}