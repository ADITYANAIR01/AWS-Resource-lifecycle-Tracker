# Changelog

All notable changes to this project will be documented here.

## [2.0.0] — 2026-04-18

### Added

- **Collectors:** Added Load Balancers collector (ALB, NLB, GLB) and NAT Gateways collector.
- **Alert Rules:** Added `load_balancer_active_too_long` and `nat_gateway_active_too_long` rules for identifying idle components accumulating hourly charges.
- **UI/UX:** Added interactive Overview metrics bars that directly link to pre-filtered resources.
- **UI/UX:** Replaced page navigation with a slide-out Details Panel for viewing resource history and snapshot data instantly.
- **UI/UX:** Added Poller Run Resource Map panel (creates, updates, deletes map) to visualize state diffs across polling intervals.
- **UI/UX:** Fully responsive design overhaul for mobile viewing and flexible grids.

### Changed

- **Config:** Added `ALERT_LOAD_BALANCER_DAYS` and `ALERT_NAT_GATEWAY_DAYS` threshold configurations heavily integrated into CloudFormation scripts.
- **Static Export:** Refactored static snapshot `generator.py` to seamlessly embed the new interactive panels without requiring external REST calls.
- **Docs:** Updated `README.md` and landing pages with latest resource tracking stats and coverage.

## [1.1.0] — 2026-04-14

### Added

- **Collectors:** Added ECS services collector (`poller/collectors/ecs.py`) with
  support for cluster/service discovery, task definition metadata, launch type,
  desired vs running counts, and tag enrichment.
- **Collectors:** Added EKS clusters collector (`poller/collectors/eks.py`) with
  nodegroup discovery, version/endpoint capture, and tag enrichment.
- **Collectors:** Added CloudFront distributions collector
  (`poller/collectors/cloudfront.py`) with global-region handling, status,
  enabled flag, origin counts, and tags.
- **Alert Rules:** Added `ecs_service_unhealthy`, `eks_cluster_pending`, and
  `cloudfront_disabled` rules with environment-driven thresholds.
- **Cost Estimation:** Added Fargate task pricing and EKS control-plane/
  nodegroup estimators in `poller/utils/cost.py`.

### Changed

- **Poller Wiring:** Registered ECS, EKS, and CloudFront collectors in
  `poller/main.py`.
- **Dashboard/UI:** Added new resource type badges, labels, and filters across
  resources/alerts/overview pages for ECS, EKS, and CloudFront.
- **Config:** Added `.env` thresholds:
  `ALERT_ECS_UNHEALTHY_MINS` and `ALERT_EKS_PENDING_MINS`.
- **Docs:** Updated README tracking matrix and landing page coverage to include
  ECS, EKS, and CloudFront.

### Fixed

- **Resource State Filtering:** Made resource state filtering case-insensitive in
  API and frontend to correctly handle mixed-case states such as `ACTIVE`,
  `PENDING`, `FAILED`, `Deployed`, and `InProgress`.
- **ECS Cost Allocation:** Reduced cross-service EC2 host double-counting by
  allocating ECS EC2 backing cost by running-task share per container instance.

---

## [1.0.1] — 2026-04-07

### Fixed

- **Security:** Flask API routes (`alerts.py`, `resources.py`) — refactored dynamic WHERE clause construction to use NULL-check parameterized pattern, eliminating SQL injection risk (defense-in-depth)

### Added

- **Security Tests:** AST-based SQL injection detector (`app/routes/test_sql_security.py`)
- **Security Tests:** Query behavior validator (`app/routes/test_query_behavior.py`)
- **Testing:** Test runner script (`run_tests.sh`) for automated security checks
- **Testing:** pytest configuration (`pyproject.toml`, `tests/conftest.py`) for future test expansion

---

## [1.0.0] — 2026-03-29

### Fixed

- `deploy-scheduled.yaml`: rewrite `.env`, `poll-and-stop.sh`, and
  `poll-and-stop.service` heredocs flush-left — indentation bleed corrupted
  all three files on disk (broken shebang, systemd parse failure, unreadable
  env keys)
- `deploy-scheduled.yaml`: add `rds:StartDBInstance` to IAM policy — without
  it every scheduled boot after the first found RDS stopped and poll failed
  silently
- `poll-and-stop.sh`: start RDS at boot before waiting for connectivity;
  check RDS status before issuing start to avoid duplicate start calls;
  extend RDS readiness timeout from 24 to 40 attempts (covers 3-5 min startup)
- `poll-and-stop.sh`: move IMDSv2 metadata fetch to top of script; raise
  token TTL from 60s to 300s; remove duplicate IMDS fetch block at bottom
- `poll-and-stop.sh`: scope `docker compose logs` with
  `--since "$(date -d "$(uptime -s)" +%s)"` — unscoped logs matched previous
  boot history causing premature EC2 stop; Unix timestamp format used instead
  of raw `uptime -s` output which Docker's Go parser does not reliably accept
- `poll-and-stop.sh`: fix `grep DB_PASSWORD` false match on
  `DASHBOARD_PASSWORD` — changed to `grep -E "^DB_PASSWORD="`
- `poll-and-stop.service`: add `network-online.target` to `After=` and
  `Wants=` — AWS API calls need network up before script executes
- `poll-and-stop.service`: raise `TimeoutStartSec` from 1800 to 2400 —
  worst-case runtime is ~1735s leaving only 65s margin; now 665s
- `UserData Step 9`: add `--build` to `docker compose up` — required on
  fresh clone where no pre-built images exist

### Added

- Phase 12: Open source release prep — CONTRIBUTING.md, CHANGELOG.md, LICENSE,
  VERSION bump to 1.0.0, GitHub repo polish.

---

- Phase 11: Landing page deployed to tracker.adityanair.tech via S3 + CloudFront
  + GitHub Actions CI/CD pipeline.

---

- Phase 10: Full documentation for both CloudFormation deployment models
  (always-on + scheduled). Deployment guides, architecture diagrams, screenshot
  walkthrough.

---

- Phase 9: CloudFormation YAML — automated provisioning of all AWS resources
  for both deployment models.

---

- Phase 8: Static snapshot export to S3 — 4 pages generated after every poll,
  uploaded to latest/ and archive/, accessible from S3 when EC2 is off.

---

- Phase 7: Full dashboard UI — dark theme, sidebar, 5 pages with server
  connectivity indicators.

---

- Phase 6: Flask dashboard backend — all API routes, auth enforcement,
  health check endpoint.

---

- Phase 5: Alert engine — all alert rules, SNS notifications, deduplication,
  auto-resolve, tag compliance checks.

---

- Phase 4: All 10 collectors active — EBS snapshots, RDS instances, RDS
  snapshots, S3, Elastic IPs, Security Groups, IAM Users, CloudWatch Alarms +
  daily cleanup jobs.

---

- Phase 3: Poller core engine — EC2 + EBS collectors, DB lock, poll cycle
  tracking, soft delete, partial failure handling verified end-to-end.

---

- Phase 2: Database schema applied to RDS — all 4 tables and 10 indexes
  created and verified.

---

- Phase 1: AWS infrastructure — VPC, EC2 (t3.micro), RDS PostgreSQL
  (db.t3.micro), IAM Role (read-only), Security Groups, Secrets Manager,
  SNS topic verified and working.

---

- Phase 0: Project skeleton — repo structure, Docker Compose, Flask health
  check, poller loop.