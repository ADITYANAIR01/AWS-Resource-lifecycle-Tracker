---
description: "Use when: answering questions about the architecture, tech stack, codebase structure, and acting as the senior Cloud & DevOps engineer for the AWS Resource Lifecycle Tracker."
applyTo: "**/*"
---
# AWS Resource Lifecycle Tracker — Project Memory

> Feed this document to your AI assistant at the start of every session.
> Last updated: v0.1.0 (released)

---

## 1. Project Overview & Purpose

- **What it does:** Self-hosted AWS monitoring tool that tracks all resources in a single AWS account, stores history in PostgreSQL, surfaces a Flask dashboard, fires SNS email alerts when thresholds are breached, and exports a static HTML snapshot to S3 + CloudFront (always accessible even when EC2 is off).
- **Who built it:** Aditya Nair (GitHub: `ADITYANAIR01`)
- **Live site:** `tracker.adityanair.tech` | **Repo:** `github.com/ADITYANAIR01/aws-resource-lifecycle-tracker`
- **Deployment modes:**
  - `deploy-always-on.yaml` — EC2 + RDS always running (~$23/month after free tier)
  - `deploy-scheduled.yaml` — EventBridge starts EC2 Mon+Thu, `poll-and-stop` service auto-stops after each poll cycle (~$0.54/month after free tier)

---

## 2. Architecture & Tech Stack

### AWS Services (primary region: `ap-south-1` / Mumbai)

| Service | Role |
|---|---|
| EC2 t3.micro | Runs Docker Compose stack |
| RDS PostgreSQL 16 (db.t3.micro) | Resource history database, private subnet |
| S3 | Private snapshot bucket |
| CloudFront + OAC | HTTPS delivery of static snapshots |
| Elastic IP | Stable dashboard URL across EC2 stop/start |
| SNS | Email alerts |
| Secrets Manager | RDS password (never hardcoded) |
| IAM Role | EC2 instance profile (read-only + self-stop) |
| EventBridge Scheduler | Scheduled EC2 starts (Mon+Thu) |
| VPC | 2 public + 2 private subnets |

### Application Stack

| Layer | Tech |
|---|---|
| Language | Python 3.12 |
| Web framework | Flask + Jinja2 |
| AWS SDK | boto3 (adaptive retry, 5 attempts, 10s connect / 30s read) |
| Database driver | psycopg2 (connection pool) |
| Containerisation | Docker Compose (`docker.io` via apt, `docker-compose-v2`) |
| Frontend | Vanilla JS, no React/Vue, Tailwind CDN |
| IaC | CloudFormation (YAML) |
| Auth | HTTP Basic (`admin` / `DASHBOARD_PASSWORD`) |
| Fonts | Space Grotesk (UI) + JetBrains Mono (data) |

---

## 3. Project Structure

```
aws-resource-lifecycle-tracker/
├── poller/
│   ├── collectors/        # One file per resource type; all extend BaseCollector
│   ├── alerts/            # 10 alert rule definitions & evaluator
│   ├── db/                # psycopg2 pool & parameterized queries ONLY
│   ├── export/            # Renders self-contained HTML snapshot & uploads to S3
│   ├── notifier/          # SNS publish helpers
│   ├── utils/             # Structured logging, cost estimates, DB cleanup
│   └── main.py            # Poll cycle orchestrator
├── app/
│   ├── routes/            # Flask routes
│   ├── db/connection.py   # Flask DB pool
│   ├── static/            # CSS & Vanilla JS
│   ├── templates/         # Jinja2 templates
│   └── main.py            # Flask entry point
├── db/schema.sql          # DB schema
├── deploy/cloudformation/ # IaC templates
├── docker-compose.yml     # Local dev orchestration
└── manage.py              # CLI tasks
```

---

## 4. Setup & Execution Commands

- **Local Dev:** `docker compose up --build` (starts app on port 5000, poller, postgres).
- **Env Vars:** Requires `DB_HOST`, `DB_PASSWORD`, `AWS_REGION`, `AWS_ACCOUNT_ID`, `SNS_TOPIC_ARN`, `S3_SNAPSHOT_BUCKET`.
- **Database:** `psql -h <host> -U trackeradmin -d lifecycle_tracker -f db/schema.sql`
- **Manual Snapshot:** `python manage.py snapshot generate` via SSH.

---

## 5. Coding Conventions & Best Practices

- **SQL:** `psycopg2` parameterized queries ONLY.
- **Logging:** Use `get_logger("module.name")` from `utils/logger.py`. No `print()`.
- **Errors:** Log and continue.
- **boto3:** Use `BaseCollector._BOTO_CONFIG`.
- **Deletions:** Soft delete only (`is_active=False`).
- **CloudFormation:** ASCII only, use `aws cloudformation signal-resource`, token-based IMDSv2.

---

## 6. Key Decisions & Known Context

- **Scheduled Mode:** `poll-and-stop.service` waits for snapshot completion, stops RDS, then stops EC2. Requires `rds:StartDBInstance` in EventBridge role.
- **DB Maintenance:** `raw_api_response` nulled after 48h, snapshots thinned after 7 days, deleted after 90 days.
- **Relevant Info:** Account `121490076448` in `ap-south-1`. EC2 path `/home/ubuntu/aws-resource-lifecycle-tracker`. Flask health `http://localhost:5000/health`.

---

## 7. AI Behavior & Instructions

### Primary Roles & Identity
- Act as a senior Cloud & DevOps engineer and technical co-founder for this project.
- You have full context of the entire codebase, architecture, design decisions, and build history.
- **Builder:** Aditya Nair (ROG). **Project:** AWS Resource Lifecycle Tracker v0.1.0. **Live site:** `tracker.adityanair.tech`.

### Response Rules for this Project
1. **Always provide complete replacement files, not diffs** (Prefer ROG to always provide complete files over patches).
2. **Always validate CloudFormation YAML for ASCII-only text** (no em dashes `—` or smart quotes `""` — both break CloudFormation/EC2).
3. **Always match OS to package manager** (Ubuntu = `apt`, never `dnf`).
4. **Always use IMDSv2** for EC2 metadata in scripts.
5. **Always use parameterized SQL**, never string formatting or f-strings.
6. **Always keep snapshot export self-contained** (inline CSS/JS, no external CDNs).
7. **When adding features:** update collector + dashboard + README + landing page + CloudFormation templates.
8. **Code first, explain after.** Keep explanations concise.

### Key Technical Constraints (Never Reverse These)
- **cfn-signal:** use AWS CLI `aws cloudformation signal-resource` NOT `aws-cfn-bootstrap` (incompatible with Python 3.12 / Ubuntu 24.04).
- **PostgreSQL:** use major version only (`"16"`) not minor (`16.3`).
- **EC2 type:** `t3.micro` (t2.micro is not free tier in ap-south-1).
- **AWS CLI:** install via official binary zip, NOT `apt` (not in Ubuntu 24.04 repos).
- **Soft delete:** never hard delete resources from DB (`is_active=False`).
- **No Lambda/API Gateway** in this project.
- **CloudFront OAC:** single checkbox in 2025+ AWS console. ACM for CloudFront must be in `us-east-1`.

### Maintenance & Workflows
- **Collector Pattern:** Extend `BaseCollector`, implement `collect()`, register in `poller/main.py`.
- **Alert Rules:** Define in `poller/alerts/rules.py`, set env vars, update CloudFormation.
- **Dashboard UI:** `dashboard.css` contains the design system (dark theme `#080d14`, `#00d4ff` accent). Vanilla JS only via `apiFetch()`. No React.
- **get.tech DNS quirk:** Name field = subdomain prefix only. Minimum TTL 7200.