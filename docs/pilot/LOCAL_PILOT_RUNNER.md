# Quantum Local Pilot Runner

Status: `INTERNAL PILOT CANDIDATE`  
Release status: `RELEASE_BLOCKED`

The runner executes one approved marketplace dataset on a project-owner-controlled computer. It is not a public server, production deployment, marketplace integration service, or permission to use an arbitrary commercial file.

## Security boundary

The local pilot is allowed only when all of the following remain true:

- host is exactly `127.0.0.1`;
- one operator and one organization;
- marketplace access is read-only;
- marketplace write methods and write credentials are absent;
- production credentials and public/LAN hosting are disabled;
- the source file is a relative `.xlsx` or `.zip` path beside the manifest;
- every dataset has owner authority, retention, admission and reconciliation evidence;
- raw rows are not copied to GitHub, CI, issue text, screenshots, external model prompts or evidence output.

Local full-disk and application-level encryption are optional for this loopback-only single-user pilot. Hosted, shared, removable, exported and backup storage remains outside this exception.

## Commands

From a checkout with Python 3.12+ and `PYTHONPATH=src`:

```powershell
python -m quantum.pilot.cli validate .\pilot.json
python -m quantum.pilot.cli run .\pilot.json --workspace .\.quantum-local
python -m quantum.pilot.cli purge --workspace .\.quantum-local `
  --tenant-id tenant-1 --run-id pilot-run-001 `
  --purged-at 2026-07-02T00:02:00Z
```

After package installation, the equivalent entry point is:

```powershell
quantum-local-pilot validate .\pilot.json
quantum-local-pilot run .\pilot.json --workspace .\.quantum-local
```

All successful output is JSON on stdout. Known failures produce JSON on stderr and exit code `2`. Unexpected internal failures produce the stable code `PILOT_INTERNAL_ERROR` and exit code `3`; traceback and raw payload are not printed.

## Manifest

The authoritative runtime contract is `quantum-local-pilot-manifest-v1`. A descriptive schema is available at:

```text
schemas/local-pilot-manifest.schema.json
```

The manifest explicitly contains:

- run and loopback scope;
- ordered timestamps;
- dataset declaration, authority and retention deadline;
- approved XLSX structural policy;
- independent dataset and storage verification controls;
- explicit B1b finance requests;
- finance-to-dataset normalization evidence hashes;
- source control totals;
- explicit finance-result-to-reconciliation bindings;
- versioned B2 reconciliation policy.

The source snapshot does not accept dataset identity from the operator. The runner injects the declared dataset UUID and the SHA-256 calculated from the local source bytes.

## Workspace

Each run receives an isolated directory:

```text
<workspace>/runs/<tenant-id-sha256>/<run-id>/
  raw/
  quarantine/
  admitted/
  derived/
  evidence/
  .quantum-local-pilot-v1.json
```

The source bytes are written once to `raw` and `quarantine`. The admitted copy is created only after the admission state reaches `ADMITTED`. Files cannot be overwritten. Paths must remain inside the workspace, and symbolic links are rejected.

`derived/operator-result.json` is a local operator artifact and may contain calculated financial values. It must not be uploaded to GitHub or sent to an external model.

`evidence/pilot-evidence.json` is privacy-reduced. It contains hashes, typed states, admission metadata, reconciliation state and documented limitations, but not raw rows or calculated financial values.

A failed run writes only:

```text
evidence/failure.json
```

with the stable error code and `RELEASE_BLOCKED` state.

## Deletion rehearsal

`purge` validates the workspace marker and rejects symbolic links before deleting the run directory. It does not delete the original source file beside the manifest. A deletion receipt is written under:

```text
<workspace>/deletion-receipts/
```

The receipt contains counts, hashes and the deletion timestamp, not deleted commercial values.

## Acceptance meaning

A successful command returns `RECONCILED`, but it does not by itself authorize production release. The evidence continues to state:

- row-level normalization evidence is supplied externally by an approved adapter;
- backup/restore evidence is still required where backups are used;
- independent exact-head review is required;
- production release remains blocked.

Real commercial data must not be used until the exact runner candidate has passed CI, independent review and the dataset-specific admission checklist.
