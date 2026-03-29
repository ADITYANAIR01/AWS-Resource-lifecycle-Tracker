# Changelog

All notable changes to this project will be documented here.

## [1.0.0] — 2026-03-29

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