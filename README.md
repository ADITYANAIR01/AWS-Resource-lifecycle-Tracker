
# AWS Resource Lifecycle Tracker

🚀 **WEBSITE LIVE :** [https://tracker.adityanair.tech](https://tracker.adityanair.tech)

## Quick Links

- [CloudFormation Deployment Guides](#cloudformation-deployment)

- [Local Development](#local-development)
- [Architecture](#architecture)
- [Features](#features)
- [Contributing](#contributing)

---

## Features

- Unified dashboard for all AWS resources
- Cost tracking and resource age insights
- Automated alerts for forgotten or risky resources
- Scheduled or always-on deployment options
- Export to S3 for offline viewing
- Read-only IAM policy (safe by default)

---

## Demo

![Dashboard Screenshot](images/aws-resource-lifecycle-tracker-087.png)

---

## Requirements

- AWS account with sufficient read-only permissions
- Docker & Docker Compose
- Python 3.8+
- (For deployment) Ability to launch CloudFormation stacks

---

> Track every AWS resource. Know what's running, what's forgotten, and what's costing you money.

**open source · Self-hosted · AWS-native · Free tier compatible.**

🌐 [tracker.adityanair.tech](https://tracker.adityanair.tech) | ⭐ Star this repo if it helps you

---

## What It Does

A self-hosted tool that monitors your AWS account and gives you a unified view of every resource — when it was created, how long it has been running, its current state, its tags, and an estimated cost. Alerts you when something looks wrong.

---

## What It Tracks

| Resource | API Used | Coverage / Cost Honesty |
| --- | --- | --- |
| EC2 Instances | `describe_instances` | On-demand ap-south-1 rates; unknown types → $0 |
| EBS Volumes | `describe_volumes` | Monthly GB-prorated; unknown types → $0 |
| EBS Snapshots | `describe_snapshots` | $0.05/GB-month prorated |
| RDS Instances | `describe_db_instances` | On-demand rates; unknown classes → $0 |
| RDS Snapshots | `describe_db_snapshots` | Age-based placeholder |
| S3 Buckets | `list_buckets` + `get_bucket_tagging` | Cost N/A → tracked at $0 (Storage Lens required) |
| Elastic Load Balancers (ALB/NLB/GLB) | `describe_load_balancers` + `describe_tags` | ELBv2 only — classic ELB excluded; base hourly only, no LCU charges |
| NAT Gateways | `describe_nat_gateways` | Base hourly only, no data-processing $/GB |
| Elastic IPs | `describe_addresses` | Unassociated only billed; 1-hour $0.005 floor until duration accrues |
| Security Groups | `describe_security_groups` | $0; ENI-based in-use check, fail-closed on ENI errors |
| IAM Users | `list_users` + `get_access_key_last_used` | $0; inactivity via `last_activity_at` (migration 001), NULL = no alert |
| CloudWatch Alarms | `describe_alarms` | MetricAlarms only — composite alarms excluded; $0 |
| ECS Services | `list_clusters` + `list_services` + `describe_services` | Fargate vCPU/GB-hour model; EC2-backed cost shared by task fraction |
| EKS Clusters | `list_clusters` + `describe_cluster` + `describe_nodegroup` | $0.10/hr control plane + nodes at first listed instance type only |
| CloudFront Distributions | `list_distributions` + `list_tags_for_resource` | $0.01/day placeholder — not usage-based |
| VPCs | `describe_vpcs` | $0; no hourly charge |
| Subnets | `describe_subnets` | $0; no hourly charge |
| Route Tables | `describe_route_tables` | $0; main/associated/unassociated derived from associations |
| Internet Gateways | `describe_internet_gateways` | $0; attached/detached derived from VPC attachments |
| VPC Endpoints | `describe_vpc_endpoints` | Gateway type $0; Interface/GWLB ~$0.01/hr baseline, no data-processing $/GB |

> All cost figures are directional on-demand approximations (ap-south-1). They exclude data transfer, Reserved Instances / Savings Plans, Spot pricing, and free-tier credits. Always confirm in AWS Cost Explorer.

---

## Architecture

```text
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

## CloudFormation-Deployment

You can deploy AWS Resource Lifecycle Tracker in two ways:

### Always-On Mode

- The dashboard and poller run 24/7 (higher cost, instant access).
- See the full guide: [Always-On Deployment Guide](CloudFormation/always-on-docs.md)

### Scheduled Mode (Recommended for Cost Savings)

- The dashboard and poller run only on a schedule (e.g., twice a week), then automatically stop to minimize costs. Elastic IP keeps the dashboard URL stable.
- See the full guide: [Scheduled Deployment Guide](CloudFormation/scheduled-docs.md)

---
***Both guides include step-by-step instructions, screenshots, prerequisites, and cleanup steps.***

---

## Local Development

```bash
git clone https://github.com/ADITYANAIR01/aws-resource-lifecycle-tracker
cd aws-resource-lifecycle-tracker
cp .env.example .env
# Edit .env with your values
docker compose up --build
```

Open [localhost:5000](http://localhost:5000)

Health check: <http://localhost:5000/health>

**Run security tests:** `./run_tests.sh`

---

## 👨‍💻 Author

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for security rules, local setup, and PR guidelines.

---

Aditya Nair

- GitHub: [@ADITYANAIR01](https://github.com/ADITYANAIR01)
- LinkedIn: [linkedin.com/in/adityanair001](https://www.linkedin.com/in/adityanair001)

### License

- [MIT LICENSE](LICENSE)

- Built by [Aditya Nair](https://www.adityanair.tech)
