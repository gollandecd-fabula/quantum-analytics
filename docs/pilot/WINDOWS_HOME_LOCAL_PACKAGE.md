# Quantum Windows HOME_LOCAL package

Status: **CONTROLLED LOCAL PILOT CANDIDATE — RELEASE_BLOCKED**

This package supports an owner-controlled local pilot. It does not authorize merge to protected `main`, public/LAN exposure, marketplace writes, production credentials or public production release.

## Primary one-click start

1. Verify the distributed archive SHA-256 against the separately provided checksum.
2. Extract the ZIP outside OneDrive, Dropbox, Google Drive and other synchronized folders.
3. Double-click `START_QUANTUM.cmd`.

The same process then:

1. validates every packaged file against `manifest.sha256.json`;
2. installs or repairs `%LOCALAPPDATA%\QuantumLocalProduction`;
3. preserves existing `config`, `data` and `output`;
4. checks Python 3.12+ and installed runtime readiness;
5. reuses a ready config or starts the safe first-run configurator;
6. opens XLSX selection;
7. performs Microsoft Defender scan;
8. requires `AUTHORIZE`;
9. displays the discovered sheet, header row and headers;
10. requires `REVIEWED`;
11. performs strict admission/import;
12. opens the local dashboard/output when available.

The installer creates `%LOCALAPPDATA%\QuantumLocalProduction\START_QUANTUM.cmd` and, when Windows permits, a desktop shortcut named `Quantum HOME_LOCAL`.

## Recovery commands

The previous commands remain available:

- `INSTALL_HOME_LOCAL.cmd` — install/repair only;
- `CONFIGURE_HOME_LOCAL.cmd` — configuration only;
- `IMPORT_XLSX.cmd` — import only.

## Security boundaries

- Use only on a project-owner-controlled home computer.
- HOME_LOCAL remains loopback-only and single-user.
- Do not place package data in OneDrive, Dropbox, Google Drive, Git, shared folders or removable media.
- Do not upload real reports, configs, storage zones or output reports to GitHub.
- Microsoft Defender or an equivalent local scan is required before import. `-SkipDefenderScan` remains an explicit operator attestation.
- `AUTHORIZE` confirms lawful authority to process the selected file.
- `REVIEWED` is requested only after the discovered candidate is displayed.
- Discovery preview and selected-file SHA-256 binding remain mandatory.
- Automatic extraction of XLSX rows into finance inputs is not implemented.
- `ADMISSION_ONLY` performs validation and admission without inventing finance values.
- `FULL` mode requires a complete explicit `finance_request`; no cost, tax or expense value is guessed.
- Marketplace writes remain disabled.

## Installation behavior

Default target:

```text
%LOCALAPPDATA%\QuantumLocalProduction
```

The package manifest is validated before target mutation. Existing `config`, `data` and `output` directories are preserved. A previous runtime is moved to `src.backup_<timestamp>` before the staged runtime replaces it.

Known cloud-synchronized package and target locations are rejected by the one-click orchestrator.

## First configuration

When no ready configuration exists, the same one-click process starts the configurator. Enter:

- report period start;
- report period end;
- retention deadline;
- local source identifier.

The wizard creates `config\default-home-local.json` in `ADMISSION_ONLY` mode. It does not create synthetic finance values. An invalid existing default config is preserved as a timestamped backup before replacement.

## Import and output

The import workflow:

1. selects one `.xlsx` file;
2. scans it with Microsoft Defender or records an explicit equivalent-scan attestation;
3. requires `AUTHORIZE`;
4. performs discovery-only preview;
5. displays file SHA-256, sheet, header row, columns and headers;
6. requires `REVIEWED` only after display;
7. confirms the file did not change after review;
8. runs strict admission;
9. writes a timestamped JSON result under `output`;
10. creates the immutable output bundle, Excel report and interactive dashboard when source processing reaches that stage.

Expected safe first-run status:

```text
ADMISSION_COMPLETE
```

This means the file passed admission. It does not mean full financial calculation or production release approval occurred.

## Full financial mode

A ready production config may set:

```json
{
  "execution_mode": "FULL",
  "finance_request": { "...": "complete versioned request" }
}
```

`FULL` remains blocked unless the request passes the strict finance contract. Cost, tax, expenses and report totals are never inferred or defaulted.

## Non-interactive one-click run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\one_click_home_local.ps1 `
  -PackageRoot . `
  -File C:\Reports\report.xlsx `
  -ReportingPeriodStart 2026-07-01 `
  -ReportingPeriodEnd 2026-07-31 `
  -RetentionDeadline 2027-07-31 `
  -SourceInternalId wb-july-2026 `
  -NonInteractive `
  -AuthorityAttested `
  -SchemaReviewed `
  -NoOpenResult
```

Non-interactive mode still performs discovery preview and file-hash binding. Attestation switches only replace keyboard confirmations and must be explicitly supplied.

## Rollback

1. Stop any Quantum local process.
2. Rename current `%LOCALAPPDATA%\QuantumLocalProduction\src`.
3. Rename the latest `src.backup_<timestamp>` back to `src`.
4. Restore a launcher backup if required.
5. Do not delete `config`, `data` or `output`.

## Remaining limitations

- Finance-request values are not extracted from XLSX rows.
- Durable authentication, queueing, database-backed sessions, backup/restore proof and deletion rehearsal remain outside this package.
- Manifest validation detects package corruption and modification but is not a substitute for external archive checksum verification or code signing.
- A successful local import does not assert public-production readiness.
