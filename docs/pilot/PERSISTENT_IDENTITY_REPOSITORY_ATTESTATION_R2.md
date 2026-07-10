# P2.2 Persistence Attestation R2

The authoritative repository is `src/quantum/pilot/persistence_v2.py`. The R1 repository remains a reviewed baseline only.

Trusted restore requires a complete `AttestedCheckpointReceipt`. The receipt binds checkpoint ID, canonical state SHA-256, expected schema SHA-256, creation time, schema version, and record count. Digest-only loading is disabled in the authoritative API.

Before initialization, save, trusted load, status, or backup, the repository fingerprints all `pilot_*` table and trigger definitions from `sqlite_master` and compares them with a clean schema generated from the reviewed schema source. Missing triggers, altered tables, and unexpected pilot schema objects fail closed.

The R2 regression set runs all 24 R1 behaviors against the R2 implementation through a test-local compatibility adapter and adds eight strict attestation scenarios. Total authoritative R2 coverage is 32 tests with resource warnings treated as errors.

This remains a synthetic-only SQLite reference. Encryption at rest, a durable external receipt store, live runtime integration, production migrations, multi-instance storage, and real-data restore rehearsal remain mandatory blockers.

`RELEASE_BLOCKED`
