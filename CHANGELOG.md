# Changelog

All notable changes to this project will be documented here.

## [0.1.0] — In Progress

### Infrastructure
- Phase 1: AWS infrastructure provisioned — VPC, EC2 (t2.micro), RDS PostgreSQL (db.t3.micro), IAM Role (read-only), Security Groups, Secrets Manager, SNS topic
- Phase 1: IAM Role verified — EC2 calls AWS APIs without credentials
- Phase 1: RDS verified — EC2 connects to PostgreSQL in private subnet

### Added
- Phase 0: Project skeleton — repo structure, Docker Compose, Flask health check, poller loop
- Phase 1: AWS infrastructure — VPC, EC2 (t2.micro), RDS PostgreSQL (db.t3.micro), IAM Role (read-only), Security Groups, Secrets Manager, SNS topic verified and working
- Phase 2: Database schema applied to RDS — all 4 tables and 10 indexes created and verified
- Phase 3: Poller core engine — EC2 + EBS collectors, DB lock, poll cycle tracking, soft delete, partial failure handling verified end-to-end
- Phase 4: All 10 collectors active — EBS snapshots, RDS instances, RDS snapshots, S3, Elastic IPs, Security Groups, IAM Users, CloudWatch Alarms + daily cleanup jobs