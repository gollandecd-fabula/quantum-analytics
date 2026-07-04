# Quantum Windows HOME_LOCAL package

Status: **INTERNAL REPAIR CANDIDATE — RELEASE_BLOCKED**

This package repairs the local Windows execution path. It does not authorize merge to protected `main`, deployment, public/LAN exposure, marketplace writes, production credentials, or a public pilot.

## Confirmed defects repaired

1. **Windows atomic-write lock** — the prior runner called `os.replace()` while `NamedTemporaryFile` was still open. The repaired runner closes and flushes the handle before replacement.
2. **OOXML package-root relationships** — valid targets such as `/xl/styles.xml` and `/xl/worksheets/sheet1.xml` are normalized to package-relative paths while URI, UNC, drive-letter and traversal targets remain rejected.
3. **Hard-coded `Sheet1` and header row 1** — HOME_LOCAL discovery identifies a candidate sheet and contiguous header row, then runs the normal strict schema inspector with the discovered exact sheet name, row index, header hash and column count.
4. **False encryption attestation** — HOME_LOCAL does not ask the operator to claim `ENCRYPTED`. The output records `HOME_LOCAL_UNENCRYPTED_STORAGE` and `PHYSICAL_ACCESS_RISK_ACCEPTED` limitations.
5. **Opaque failures** — the Windows runner returns a stable code and exception type. Full message/traceback is emitted only with `--debug-errors`.
6. **Damaged ACL installation** — the installer restores inherited ACLs under `%LOCALAPPDATA%\QuantumLocalProduction` and preserves `config`, `data` and `output`.
7. **Non-reproducible package** — the repository now contains a package builder, installer, launcher, configuration template, tests and a Windows CI artifact workflow.

## Security boundaries

- Use only on a project-owner-controlled home computer.
- HOME_LOCAL remains loopback-only and single-user.
- Do not place the package data directory in OneDrive, Dropbox, Google Drive, Git, shared folders or removable media.
- Do not upload real reports, configs, storage zones or output reports to GitHub.
- Microsoft Defender or an equivalent scan is required before import unless the launcher is explicitly invoked with `-SkipDefenderScan` after an equivalent scan.
- `AUTHORIZE` confirms lawful authority to process the selected file.
- `REVIEWED` approves the discovered sheet/header candidate for this selected report. It is not a blanket schema approval.
- Automatic extraction of report rows into the financial request is not implemented. Cost, tax and other expenses remain explicit user/config inputs.

## Build

From the repository root on Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\windows\build_local_production.ps1
```

Expected archive:

```text
dist\QuantumLocalProduction_HOME_LOCAL.zip
```

The package contains `manifest.sha256.json` and the workflow publishes the ZIP as a GitHub Actions artifact.

## Install over the current local copy

1. Extract the ZIP outside any cloud-synchronized folder.
2. Run `INSTALL_HOME_LOCAL.cmd`.
3. The installer preserves these existing directories:
   - `config`
   - `data`
   - `output`
4. The old source runtime is moved to `src.backup_<timestamp>`.
5. Existing launcher scripts are backed up before replacement.

Default target:

```text
%LOCALAPPDATA%\QuantumLocalProduction
```

## Import

Run:

```text
%LOCALAPPDATA%\QuantumLocalProduction\IMPORT_XLSX.cmd
```

The launcher:

1. selects an `.xlsx` file;
2. scans it with Microsoft Defender;
3. requires `AUTHORIZE`;
4. requires `REVIEWED` for automatic sheet/header discovery;
5. uses the first existing configuration in this order:
   - `config\production.local.json`
   - `config\default-home-local.json`
   - `config\default-production.json`
   - package template;
6. writes the JSON result to `output`.

## Non-interactive invocation

Non-interactive mode requires explicit switches. It never silently asserts authority or review:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\import_source.ps1 `
  -File C:\Reports\report.xlsx `
  -Config C:\Quantum\production.local.json `
  -NonInteractive `
  -AuthorityAttested `
  -SchemaReviewed
```

## Rollback

1. Stop any Quantum local process.
2. Rename the current `%LOCALAPPDATA%\QuantumLocalProduction\src`.
3. Rename the latest `src.backup_<timestamp>` back to `src`.
4. Restore the launcher backup if required.
5. Do not delete `config`, `data` or `output`.

## Remaining limitations

- Finance-request values are not inferred from XLSX rows.
- Schema discovery is HOME_LOCAL-only and requires per-file review.
- Durable authentication, queueing, database-backed sessions, backup/restore proof and deletion rehearsal remain outside this repair.
- A successful local import does not assert `PILOT_READY` or `RELEASE_ALLOWED`.
