BEGIN;

CREATE TABLE import_batch (
    import_batch_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    marketplace_account_id TEXT NOT NULL,
    source_file_sha256 CHAR(64) NOT NULL CHECK (source_file_sha256 ~ '^[a-f0-9]{64}$'),
    source_file_name TEXT NOT NULL,
    source_file_size BIGINT NOT NULL CHECK (source_file_size >= 0),
    adapter_id TEXT,
    adapter_version TEXT,
    schema_id TEXT,
    state TEXT NOT NULL CHECK (
        state IN (
            'RECEIVED', 'FINGERPRINTED', 'ADAPTER_SELECTED', 'VALIDATING',
            'QUARANTINED', 'NORMALIZING', 'RECONCILING', 'PUBLISHED',
            'PARTIALLY_PUBLISHED', 'FAILED', 'RESTATED'
        )
    ),
    trace_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    UNIQUE (
        organization_id,
        marketplace_account_id,
        source_file_sha256,
        adapter_id,
        adapter_version
    )
);

CREATE TABLE source_record (
    source_record_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    source_row_key TEXT NOT NULL,
    raw_row_hash CHAR(64) NOT NULL CHECK (raw_row_hash ~ '^[a-f0-9]{64}$'),
    raw_payload JSONB NOT NULL,
    structural_fingerprint TEXT NOT NULL,
    semantic_fingerprint TEXT,
    validation_status TEXT NOT NULL CHECK (
        validation_status IN ('VALID', 'QUARANTINED', 'INVALID')
    ),
    quarantine_reason TEXT,
    adapter_id TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        validation_status <> 'QUARANTINED'
        OR quarantine_reason IS NOT NULL
    ),
    UNIQUE (import_batch_id, source_row_key, raw_row_hash)
);

CREATE TABLE canonical_event (
    event_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    marketplace_account_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    recognition_time TIMESTAMPTZ NOT NULL,
    stable_business_key TEXT NOT NULL,
    source_row_key TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    idempotency_key CHAR(64) NOT NULL UNIQUE CHECK (idempotency_key ~ '^[a-f0-9]{64}$'),
    semantic_payload_hash CHAR(64) NOT NULL CHECK (semantic_payload_hash ~ '^[a-f0-9]{64}$'),
    supersedes_event_id TEXT REFERENCES canonical_event(event_id),
    reversal_of_event_id TEXT REFERENCES canonical_event(event_id),
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    source_record_id TEXT NOT NULL REFERENCES source_record(source_record_id),
    schema_version TEXT NOT NULL,
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    provenance JSONB NOT NULL CHECK (jsonb_typeof(provenance) = 'object'),
    status TEXT NOT NULL CHECK (
        status IN ('VALID', 'SUPERSEDED', 'REVERSED', 'CONFLICT', 'BLOCKED')
    ),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (supersedes_event_id IS NULL OR supersedes_event_id <> event_id),
    CHECK (reversal_of_event_id IS NULL OR reversal_of_event_id <> event_id),
    UNIQUE (
        organization_id,
        marketplace_account_id,
        event_type,
        stable_business_key,
        revision,
        semantic_payload_hash
    )
);

CREATE INDEX canonical_event_business_history_idx
    ON canonical_event (
        organization_id,
        marketplace_account_id,
        stable_business_key,
        revision
    );

CREATE TABLE worker_lease (
    job_id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    lease_token TEXT NOT NULL UNIQUE,
    acquired_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    attempt_count INTEGER NOT NULL CHECK (attempt_count >= 1),
    CHECK (expires_at > acquired_at)
);

COMMIT;
