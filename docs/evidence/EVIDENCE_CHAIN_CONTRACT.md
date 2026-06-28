# Evidence Chain Contract v1

Status: `DRAFT / B3 R2`

## Purpose

An Evidence Chain is an immutable, self-contained proof graph for one Metric Result. It records exact versions and hashes needed to reproduce or reject the result without consulting mutable defaults.

## Required chain

A complete chain resolves:

`Metric Result → Metric Definition → Calculation Profile → Rounding Policy / Source Authority → Canonical Events → Transformations → Source Records → Source Files → SHA-256`.

Each referenced object has a stable ID and immutable content hash. Version-only, name-only, or latest-version references are forbidden.

## Evidence objects

### Source file evidence

Each source file entry contains:

- `source_file_id`;
- exact SHA-256;
- byte size;
- media type;
- ingestion timestamp;
- immutable storage key.

### Source record evidence

Each record contains Source Record ID, Import Batch ID, source row key, raw-row SHA-256, and source-file SHA-256. The referenced file must exist in the same chain.

### Event evidence

Each event contains Event ID, schema version, revision, semantic payload hash, Source Record ID, and source-file SHA-256. Its record and file must exist and agree.

### Transformation evidence

Each transformation contains ID, version, content hash, input hash, and output hash. Transformations are ordered explicitly; implicit code-current-at-runtime is forbidden.

### Links

Links are explicit directed edges between typed evidence objects. Every endpoint must resolve exactly once. Duplicate object identities, dangling links, or multiple conflicting hashes for one identity fail closed.

## Integrity and deterministic reproduction

The chain contains:

- `evidence_chain_id`, positive version, and `content_hash`;
- Metric Result ID/hash;
- exact Metric Definition, Calculation Profile, Rounding Policy, and Source Authority references;
- sorted evidence collections;
- `input_fingerprint` over canonical recorded inputs;
- `replay_key` identifying the deterministic reproduction request;
- actor and creation timestamp.

Canonical JSON uses UTF-8, sorted object keys, compact separators, and preserves array order where order is semantic.

To prevent a circular hash dependency, Evidence Chain `content_hash` is computed with both top-level `content_hash` and the backlink `metric_result_hash` omitted. The immutable sequence is:

1. calculate the Evidence Chain content hash without those two fields;
2. place that chain hash in `Metric Result.evidence_chain_ref`;
3. calculate the Metric Result hash without its own `result_hash`;
4. store the resulting Metric Result hash in the Evidence Chain backlink.

The backlink must equal the final Metric Result hash, but changing only the backlink does not change the Evidence Chain content hash. All other Evidence Chain fields remain covered by the hash.

Reproduction succeeds only when the recorded inputs produce the same input fingerprint, Evidence Chain hash, and Metric Result hash. A mismatch creates a new diagnostic record; it never mutates the prior snapshot.

## Typed non-valid paths

`STALE`, `BLOCKED`, `UNAVAILABLE`, and `CONFLICT` remain evidence-bearing outcomes. The chain records attempted sources, diagnostics, and missing-link reasons. They never become numeric zero and are non-publishable.

## Recalculation audit

The Metric Result audit and Evidence Chain must agree on actor, reason, timestamps, predecessor, input fingerprint, and replay key. Unknown actor, empty reason, missing predecessor for recalculation/restatement, or timestamp inversion fails closed.

## Security and scope boundary

Evidence contains no secrets and no real commercial fixtures in GitHub. This contract grants no write integration, marketplace action, financial-rule activation, deployment, or production authorization.
