-- USCIA Evidence Graph and Learning Engine Schema
-- All tables use IF NOT EXISTS — idempotent, safe to run on every startup.

-- Core investigation record
CREATE TABLE IF NOT EXISTS IncidentRecord (
    incident_id       VARCHAR(36)    PRIMARY KEY,
    material          NVARCHAR(40)   NOT NULL,
    plant             NVARCHAR(4)    NOT NULL,
    planning_version  NVARCHAR(10),
    date_range_start  DATE,
    date_range_end    DATE,
    incident_type     NVARCHAR(60)   NOT NULL,
    root_cause        NVARCHAR(60),
    confidence        NVARCHAR(10),
    report_consultant NCLOB,
    report_planner    NCLOB,
    created_at        TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    duration_seconds  INTEGER
);

-- Evidence nodes — one row per system queried per investigation
CREATE TABLE IF NOT EXISTS EvidenceNode (
    node_id         VARCHAR(36)    PRIMARY KEY,
    incident_id     VARCHAR(36)    REFERENCES IncidentRecord(incident_id),
    system_name     NVARCHAR(60)   NOT NULL,
    status          NVARCHAR(20)   NOT NULL,
    raw_payload     NCLOB,
    manual_guidance NCLOB,
    created_at      TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
);

-- Links between evidence nodes (continuity key correlations)
CREATE TABLE IF NOT EXISTS EvidenceLink (
    link_id         VARCHAR(36)    PRIMARY KEY,
    incident_id     VARCHAR(36)    REFERENCES IncidentRecord(incident_id),
    from_node_id    VARCHAR(36)    REFERENCES EvidenceNode(node_id),
    to_node_id      VARCHAR(36)    REFERENCES EvidenceNode(node_id),
    continuity_key  NVARCHAR(60),
    continuity_val  NVARCHAR(255),
    broken_boundary BOOLEAN        DEFAULT FALSE
);

-- Root cause classification and evidence tagging
CREATE TABLE IF NOT EXISTS FailureClassification (
    classification_id VARCHAR(36)   PRIMARY KEY,
    incident_id       VARCHAR(36)   REFERENCES IncidentRecord(incident_id),
    root_cause        NVARCHAR(60)  NOT NULL,
    confidence        NVARCHAR(10)  NOT NULL,
    confirmed_count   INTEGER       DEFAULT 0,
    probable_count    INTEGER       DEFAULT 0,
    missing_count     INTEGER       DEFAULT 0,
    findings          NCLOB
);

-- Recommended remediation actions (Phase 4 execution-ready)
CREATE TABLE IF NOT EXISTS RemediationRecord (
    action_id         VARCHAR(36)   PRIMARY KEY,
    incident_id       VARCHAR(36)   REFERENCES IncidentRecord(incident_id),
    action_type       NVARCHAR(40)  NOT NULL,
    action_params     NCLOB         NOT NULL,
    requires_approval BOOLEAN       DEFAULT TRUE,
    rank              INTEGER       DEFAULT 1,
    outcome           NVARCHAR(30),
    outcome_at        TIMESTAMP
);

-- Learning engine: remediation effectiveness scores
CREATE TABLE IF NOT EXISTS EffectivenessScore (
    score_id             VARCHAR(36)    PRIMARY KEY,
    root_cause           NVARCHAR(60)   NOT NULL,
    action_type          NVARCHAR(40)   NOT NULL,
    resolution_rate      DECIMAL(5,4)   DEFAULT 0.0,
    avg_resolution_hours DECIMAL(8,2)   DEFAULT 0.0,
    total_attempts       INTEGER        DEFAULT 0,
    total_resolved       INTEGER        DEFAULT 0,
    updated_at           TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (root_cause, action_type)
);
