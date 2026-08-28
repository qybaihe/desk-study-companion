-- TiDB Cloud schema for device behaviour, source snapshots, and asset manifests.

CREATE TABLE IF NOT EXISTS project_event (
    event_id VARCHAR(128) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    device_id VARCHAR(128) NOT NULL DEFAULT '',
    session_id VARCHAR(128) NOT NULL DEFAULT '',
    source VARCHAR(64) NOT NULL DEFAULT 'desk-study-companion',
    event_time DATETIME(6) NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (event_id),
    KEY idx_project_event_device_time (device_id, event_time),
    KEY idx_project_event_session_time (session_id, event_time),
    KEY idx_project_event_type_time (event_type, event_time)
);

CREATE TABLE IF NOT EXISTS project_code_snapshot (
    project_id VARCHAR(64) NOT NULL,
    git_commit CHAR(40) NOT NULL,
    path VARCHAR(512) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    language VARCHAR(64) NOT NULL DEFAULT '',
    github_url TEXT NOT NULL,
    content MEDIUMTEXT NOT NULL,
    captured_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (project_id, git_commit, path),
    KEY idx_code_snapshot_hash (content_sha256)
);

CREATE TABLE IF NOT EXISTS project_asset_manifest (
    project_id VARCHAR(64) NOT NULL,
    git_commit CHAR(40) NOT NULL,
    path VARCHAR(512) NOT NULL,
    content_sha256 CHAR(64) NOT NULL,
    size_bytes BIGINT UNSIGNED NOT NULL,
    mime_type VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream',
    github_url TEXT NOT NULL,
    captured_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (project_id, git_commit, path),
    KEY idx_asset_manifest_hash (content_sha256)
);
