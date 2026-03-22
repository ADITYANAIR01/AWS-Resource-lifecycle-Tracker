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
