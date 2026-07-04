# Quantum Windows HOME_LOCAL package

Status: **INTERNAL RED-TEAM-HARDENED CANDIDATE — RELEASE_BLOCKED**

This package repairs and hardens the local Windows execution path. It does not authorize merge to protected `main`, deployment, public/LAN exposure, marketplace writes, production credentials, or a public pilot.

## Confirmed defects repaired

1. **Windows atomic-write lock** — temporary files are closed and flushed before `os.replace()`.
2. **OOXML package-root relationships** — valid `/xl/...` targets are normalized while URI, UNC, drive-letter and traversal targets remain rejected.
3. **Hard-coded sheet/header assumptions** — schema discovery supports non-default sheet names and header rows.
4. **Decorative-row misclassification** — known financial/report header keywords now outrank wide decorative title rows.
5. **Blind schema approval** — the launcher displays file SHA-256, sheet, header row, columns and headers before `REVIEWED` can be confirmed.
6. **Review/import file swap** — the selected XLSX SHA-256 is checked before and after review.
7. **False encryption attestation** — HOME_LOCAL records unencrypted-storage limitations instead of claiming disk encryption.
8. **Opaque failures** — stable error code and exception type are returned; full trace is opt-in with `--debug-errors`.
9. **Damaged ACL installation** — managed runtime/scripts ACLs are repaired while `config`, `data` and `output` are preserved.
10. **Unverified package installation** — installer validates every packaged file against `manifest.sha256.json` and rejects missing, modified, duplicate, unsafe or unmanifested files before target mutation.
11. **Merge-ref provenance ambiguity** — Windows workflows explicitly checkout and assert the exact PR head; package `source_commit` must match it.
12. **Clean-install configuration blocker** — `CONFIGURE_HOME_LOCAL.cmd` creates a safe `ADMISSION_ONLY` configuration without inventing finance values.
13. **Placeholder malware evidence** — each import uses a temporary runtime config containing a SHA-256-bound local scan receipt.

## Security boundaries

- Use only on a project-owner-controlled home computer.
- HOME_LOCAL remains loopback-only and single-user.
- Do not place package data in OneDrive, Dropbox, Google Drive, Git, shared folders or removable media.
- Do not upload real reports, configs, storage zones or output reports to GitHub.
- Microsoft Defender or an equivalent local scan is required before import. `-SkipDefenderScan` is an explicit operator attestation that an equivalent scan was completed.
- `AUTHORIZE` confirms lawful authority to process the selected file.
- `REVIEWED` is requested only after the discovered candidate is displayed.
- Automatic extraction of XLSX rows into finance inputs is not implemented.
- `ADMISSION_ONLY` performs validation and admission without financial calculation.
- `FULL` mode requires a complete explicit `finance_request`; no cost, tax or expense values are guessed.

## Install

1. Verify the distributed archive SHA-256 against the separately provided checksum.
2. Extract the ZIP outside cloud-synchronized folders.
3. Run `INSTALL_HOME_LOCAL.cmd`.
4. The installer verifies the internal manifest before changing the target.
5. Existing `config`, `data` and `output` directories are preserved.
6. Previous runtime is moved to `src.backup_<timestamp>`.

Default target:

```text
%LOCALAPPDATA%\QuantumLocalProduction
```

## First configuration

When no ready local configuration exists, run:

```text
%LOCALAPPDATA%\QuantumLocalProduction\CONFIGURE_HOME_LOCAL.cmd
```

Enter:

- report period start;
- report period end;
- retention deadline.

The wizard creates `config\default-home-local.json` in `ADMISSION_ONLY` mode. It does not create synthetic finance values.

## Import

Run:

```text
%LOCALAPPDATA%\QuantumLocalProduction\IMPORT_XLSX.cmd
```

The launcher:

1. selects one `.xlsx` file;
2. scans it with Microsoft Defender or records an explicit equivalent-scan attestation;
3. requires `AUTHORIZE`;
4. performs discovery-only preview;
5. displays file SHA-256, sheet, header row and headers;
6. requires `REVIEWED` only after display;
7. confirms the file did not change after review;
8. runs strict admission;
9. writes the JSON result to `output`.

Expected safe first-run result:

```text
ADMISSION_COMPLETE
```

This means the file passed admission and was promoted to the admitted zone. It does not mean financial calculation or release approval occurred.

## Full financial mode

A ready production config may set:

```json
{
  "execution_mode": "FULL",
  "finance_request": { "...": "complete versioned request" }
}
```

`FULL` mode remains blocked unless the complete finance request passes the strict finance contract. Cost, tax, expenses and report totals are never inferred or defaulted.

## Non-interactive configuration

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\configure_home_local.ps1 `
  -ReportingPeriodStart 2026-07-01 `
  -ReportingPeriodEnd 2026-07-31 `
  -RetentionDeadline 2027-07-31 `
  -SourceInternalId wb-july-2026 `
  -NonInteractive
```

## Non-interactive import

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\import_source.ps1 `
  -File C:\Reports\report.xlsx `
  -Config C:\Quantum\default-home-local.json `
  -NonInteractive `
  -AuthorityAttested `
  -SchemaReviewed
```

Non-interactive mode still runs discovery preview and file-hash binding. The switches only replace keyboard confirmation.

## Rollback

1. Stop any Quantum local process.
2. Rename current `%LOCALAPPDATA%\QuantumLocalProduction\src`.
3. Rename the latest `src.backup_<timestamp>` back to `src`.
4. Restore a launcher backup if required.
5. Do not delete `config`, `data` or `output`.

## Remaining limitations

- Finance-request values are not extracted from XLSX rows.
- Durable authentication, queueing, database-backed sessions, backup/restore proof and deletion rehearsal remain outside this repair.
- Manifest validation detects package corruption and modification but is not a substitute for external archive checksum verification or code signing.
- A successful local import does not assert `PILOT_READY` or `RELEASE_ALLOWED`.
