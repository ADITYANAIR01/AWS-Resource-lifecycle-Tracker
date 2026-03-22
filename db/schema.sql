-- =============================================================================
-- AWS Resource Lifecycle Tracker — Database Schema
-- Written in Phase 0. Applied to RDS in Phase 2.
-- Run: psql -h <host> -U <user> -d <db> -f schema.sql
-- Safe to run multiple times — uses IF NOT EXISTS throughout
-- =============================================================================

CREATE TABLE IF NOT EXISTS resources (
    resource_id         VARCHAR(255)    NOT NULL,
    resource_type       VARCHAR(50)     NOT NULL,
    resource_name       VARCHAR(255),
    account_id          VARCHAR(20)     NOT NULL,
    region              VARCHAR(50)     NOT NULL,
    state               VARCHAR(50),
    created_at          TIMESTAMP,
    first_seen          TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_seen           TIMESTAMP       NOT NULL DEFAULT NOW(),
    last_modified       TIMESTAMP,
    tags                JSONB           NOT NULL DEFAULT '{}',
    estimated_cost_usd  DECIMAL(10,4)   NOT NULL DEFAULT 0,
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    deleted_at          TIMESTAMP,
    PRIMARY KEY (resource_id, resource_type)
);

CREATE TABLE IF NOT EXISTS resource_snapshots (
    id                  SERIAL          PRIMARY KEY,
    resource_id         VARCHAR(255)    NOT NULL,
    resource_type       VARCHAR(50)     NOT NULL,
    polled_at           TIMESTAMP       NOT NULL DEFAULT NOW(),
    state               VARCHAR(50),
    tags                JSONB           NOT NULL DEFAULT '{}',
    estimated_cost_usd  DECIMAL(10,4)   NOT NULL DEFAULT 0,
    raw_api_response    JSONB
);

CREATE TABLE IF NOT EXISTS alerts (
    id              SERIAL          PRIMARY KEY,
    resource_id     VARCHAR(255)    NOT NULL,
    resource_type   VARCHAR(50)     NOT NULL,
    alert_type      VARCHAR(100)    NOT NULL,
    severity        VARCHAR(20)     NOT NULL
                        CHECK (severity IN ('info', 'warning', 'critical')),
    message         TEXT            NOT NULL,
    triggered_at    TIMESTAMP       NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMP,
    notified        BOOLEAN         NOT NULL DEFAULT FALSE,
    acknowledged    BOOLEAN         NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS poller_runs (
    id                  SERIAL          PRIMARY KEY,
    started_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMP,
    resources_found     INTEGER         NOT NULL DEFAULT 0,
    resources_new       INTEGER         NOT NULL DEFAULT 0,
    resources_updated   INTEGER         NOT NULL DEFAULT 0,
    resources_deleted   INTEGER         NOT NULL DEFAULT 0,
    alerts_triggered    INTEGER         NOT NULL DEFAULT 0,
    alerts_resolved     INTEGER         NOT NULL DEFAULT 0,
    status              VARCHAR(20)
                            CHECK (status IN (
                                'running', 'success',
                                'partial_failure', 'failed'
                            )),
    error_log           TEXT
);

CREATE INDEX IF NOT EXISTS idx_resources_type        ON resources(resource_type);
CREATE INDEX IF NOT EXISTS idx_resources_active      ON resources(is_active);
CREATE INDEX IF NOT EXISTS idx_resources_account     ON resources(account_id);
CREATE INDEX IF NOT EXISTS idx_resources_type_active ON resources(resource_type, is_active);
CREATE INDEX IF NOT EXISTS idx_snapshots_resource    ON resource_snapshots(resource_id, resource_type);
CREATE INDEX IF NOT EXISTS idx_snapshots_polled_at   ON resource_snapshots(polled_at);
CREATE INDEX IF NOT EXISTS idx_alerts_resource       ON alerts(resource_id, resource_type);
CREATE INDEX IF NOT EXISTS idx_alerts_unresolved     ON alerts(resolved_at) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_alerts_unnotified     ON alerts(notified) WHERE notified = FALSE;
CREATE INDEX IF NOT EXISTS idx_poller_runs_started   ON poller_runs(started_at DESC);