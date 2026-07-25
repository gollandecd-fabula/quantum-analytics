# MILESTONE 6 — Marketplace-Neutral Core & Adapters

## Verdict

`PASS_LOCAL_PENDING_EXACT_HEAD_CI`

M6 removes the direct Wildberries dependency from the Windows source bridge and introduces an explicit, fail-closed adapter boundary. It does not authorize production release, marketplace writes, merge to `main`, automatic price or advertising changes, or a final quality score.

## Baseline

- Branch: `fix/quantum-one-click-stable-release`
- M5 exact head: `f7d2860258b93e40c253876e998360eb006859b4`
- Runtime: HOME_LOCAL, offline, read-only
- Existing Wildberries parsers and financial semantics: preserved behind the adapter

## Implemented architecture

### Neutral contract

`ReviewedSourceRequest` carries reviewed payload bytes, schema discovery, inspection limits, source identity, source context and source format without embedding a marketplace-specific report schema.

Every adapter must expose:

- canonical `marketplace_id`;
- unique `adapter_id`;
- adapter `schema_version`;
- `bridge_reviewed_source(request)`.

The registry adds common result metadata and rejects adapter outputs that attempt to enable marketplace writes or expose raw source rows.

### Registry and composition boundary

`MarketplaceAdapterRegistry` owns adapter registration, canonical marketplace lookup and dispatch. Duplicate registrations, unknown marketplaces and mutation after registry freeze fail closed.

The default composition root registers two independent adapters:

1. `WILDBERRIES` — wraps the already validated WB dispatcher without changing its financial interpretation.
2. `OZON` — establishes the adapter boundary but returns `SOURCE_BRIDGE_BLOCKED` until an approved Ozon semantic source profile exists. It does not infer financial meaning from unknown columns.

Future marketplaces can be added by registration rather than by editing finance, insights, recommendations or Windows orchestration.

### Windows integration

`windows_source_bridge.py` no longer imports or calls `bridge_reviewed_wb_source`. It requires an explicit marketplace identifier, normalizes aliases such as `WB`, builds a neutral request and delegates through the registry. Missing or unregistered marketplaces produce explicit reason codes and do not change admission state.

## Red Team findings and closure

- `M6-D001 P1` — direct WB import in Windows orchestration: closed.
- `M6-D002 P1` — no enforceable adapter contract or registry: closed.
- `M6-D003 P1` — adapter result could theoretically claim marketplace writes: closed by invariant.
- `M6-D004 P2` — missing marketplace could be silently interpreted: closed; explicit value is required.
- `M6-D005 P2` — Ozon boundary absent: closed with a registered fail-closed adapter; semantic parsing remains blocked pending approved schemas.
- `M6-D006 P2` — architecture drift could reintroduce concrete imports into core: closed with source-boundary regression tests.

## Safety preserved

- marketplace writes remain disabled in every adapter result;
- raw rows remain excluded from reports;
- no external network calls were added;
- no financial assumptions or hard-coded product costs, taxes or other expenses were added;
- recommendation generation remains separate from execution;
- unknown marketplace and unknown Ozon schemas fail closed;
- existing Wildberries parsers remain isolated under `quantum.adapters.wildberries`.

## Local validation

- Python syntax/compile validation for all M6 files: PASS;
- neutral contract and registry focused tests: 8/8 PASS;
- adapter write-boundary negative test: PASS;
- Ozon fail-closed contract test: PASS;
- architecture import-boundary tests: PASS;
- revised Windows source bridge contract tests: 6/6 PASS in the reconstructed focused harness;
- exact-head repository CI: required after commit and push.

## Limitations

- Ozon semantic report profiles are not yet approved or implemented; the Ozon adapter intentionally returns `SOURCE_BRIDGE_BLOCKED`.
- No live marketplace APIs are called and no marketplace write credentials are accepted.
- Full cross-platform regression evidence depends on exact-head GitHub Actions after push.
- Production release and scoring remain blocked until later milestones and Final Red Team.
