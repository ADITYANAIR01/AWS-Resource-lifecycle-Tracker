"""
IAM users collector.

Collects all IAM users in the account.
IAM is a global service — region is stored as 'global'.

For each user we track:
  - Creation date
  - Last activity (most recent of: console login, access key last used)
  - Active access keys count
  - Tags

We do NOT collect or store:
  - Passwords
  - Secret access keys
  - Policy details
  - Permission boundaries

last_modified is set to the most recent activity timestamp.
State: 'active' if activity within threshold, 'inactive' if not.
The actual alerting threshold is evaluated in Phase 5 alert engine —
here we just store the raw last-activity date.
"""

from datetime import datetime, timezone

from collectors.base import BaseCollector


class IAMUserCollector(BaseCollector):

    RESOURCE_TYPE = "iam_user"

    def collect(self) -> list:
        # IAM is global — region stored as 'global'
        client    = self._make_client("iam")
        resources = []

        self.logger.info("Collecting IAM users")

        try:
            paginator = client.get_paginator("list_users")

            for page in paginator.paginate():
                for user in page.get("Users", []):

                    username    = user["UserName"]
                    create_time = user.get("CreateDate")
                    user_arn    = user.get("Arn", "")

                    # Get tags for this user
                    tags = self._fetch_user_tags(client, username)

                    # Get last activity across all access keys
                    last_activity = self._get_last_activity(
                        client, username, user
                    )

                    # State based on whether we found any activity timestamp
                    state = "active" if last_activity else "inactive"

                    resources.append({
                        "resource_id":        user_arn or username,
                        "resource_type":      self.RESOURCE_TYPE,
                        "resource_name":      username,
                        "account_id":         self.account_id,
                        "region":             "global",
                        "state":              state,
                        "created_at":         create_time,
                        "tags":               tags,
                        "estimated_cost_usd": 0,
                        "raw_api_response":   {
                            **user,
                            "last_activity": (
                                last_activity.isoformat()
                                if last_activity else None
                            ),
                        },
                    })

        except Exception as e:
            self.logger.error(f"IAM user collection failed: {e}")
            raise

        self.logger.info(f"Collected {len(resources)} IAM user(s)")
        return resources

    def _get_last_activity(self, client, username: str, user: dict):
        """
        Find the most recent activity timestamp for a user.
        Checks: console password last used + each access key last used.
        Returns the most recent datetime or None if no activity found.
        """
        timestamps = []

        # Console last login
        password_last_used = user.get("PasswordLastUsed")
        if password_last_used:
            timestamps.append(password_last_used)

        # Access key last used
        try:
            keys_response = client.list_access_keys(UserName=username)
            for key in keys_response.get("AccessKeyMetadata", []):
                key_id = key.get("AccessKeyId")
                if not key_id:
                    continue
                try:
                    used_response = client.get_access_key_last_used(
                        AccessKeyId=key_id
                    )
                    last_used = used_response.get(
                        "AccessKeyLastUsed", {}
                    ).get("LastUsedDate")
                    if last_used:
                        timestamps.append(last_used)
                except Exception:
                    # If we can't get last used for a key, skip it
                    pass
        except Exception as e:
            self.logger.warning(
                f"Could not fetch access keys for user {username}: {e}"
            )

        if not timestamps:
            return None

        # Normalise all timestamps to UTC-aware
        aware = []
        for ts in timestamps:
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            aware.append(ts)

        return max(aware)

    def _fetch_user_tags(self, client, username: str) -> dict:
        """Fetch tags for an IAM user. Returns {} on failure."""
        try:
            response = client.list_user_tags(UserName=username)
            return self._extract_tags(response.get("Tags", []))
        except Exception as e:
            self.logger.warning(
                f"Could not fetch tags for IAM user {username}: {e}"
            )
            return {}