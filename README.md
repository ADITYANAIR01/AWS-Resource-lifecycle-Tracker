# AWS Resource Lifecycle Tracker

> Track every AWS resource. Know what's running, what's forgotten, and what's costing you money.

**Open source · Self-hosted · AWS-native · Free tier compatible**

🌐 [tracker.adityanair.tech](https://tracker.adityanair.tech) | ⭐ Star this repo if it helps you

---

## What It Does

A self-hosted tool that monitors your AWS account and gives you a unified view of every resource — when it was created, how long it has been running, its current state, its tags, and an estimated cost. Alerts you when something looks wrong.

---

## What It Tracks

| Resource | API Used |
|---|---|
| EC2 Instances | `describe_instances` |
| EBS Volumes | `describe_volumes` |
| EBS Snapshots | `describe_snapshots` |
| RDS Instances | `describe_db_instances` |
| RDS Snapshots | `describe_db_snapshots` |
| S3 Buckets | `list_buckets` + `get_bucket_tagging` |
| Elastic IPs | `describe_addresses` |
| Security Groups | `describe_security_groups` |
| IAM Users | `list_users` + `get_access_key_last_used` |
| CloudWatch Alarms | `describe_alarms` |

---

## Architecture
```
EventBridge (scheduled)
      |
      v
  EC2 t2.micro
  +---------------------------+
  | Poller (Python + boto3)   |  --> AWS APIs (read-only)
  | Flask Dashboard           |  --> RDS PostgreSQL
  | Static Export Generator   |  --> S3 (snapshot)
  | manage.py CLI             |
  +---------------------------+
      |                |
      v                v
  RDS PostgreSQL    S3 Bucket
  (always on)       latest/     <-- viewable when EC2 is OFF
                    archive/
```

---

## Local Development
```bash
git clone https://github.com/ADITYANAIR01/aws-resource-lifecycle-tracker
cd aws-resource-lifecycle-tracker
cp .env.example .env
# Edit .env with your values
docker compose up --build
```

Open http://localhost:5000
Health check: http://localhost:5000/health

---

## License

[MIT](LICENSE) · Built by [Aditya Nair](https://www.adityanair.tech)