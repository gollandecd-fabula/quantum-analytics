# One-click HOME_LOCAL launcher R1

Status: `LOCAL_PILOT_DEPLOY_R1 / ONE_CLICK_INSTALL`

## Purpose

`START_QUANTUM.cmd` is the single user-facing entry point for the controlled HOME_LOCAL pilot. A first click verifies and installs the package, creates a safe configuration when necessary, starts the reviewed XLSX import and opens the local result. Subsequent clicks use the installed launcher and do not reinstall the runtime.

The launcher does not remove the existing recovery commands. `INSTALL_HOME_LOCAL.cmd`, `CONFIGURE_HOME_LOCAL.cmd` and `IMPORT_XLSX.cmd` remain available for repair and isolated troubleshooting.

## First-run sequence

1. Resolve and validate the extracted package path.
2. Reject known OneDrive, Dropbox and Google Drive locations.
3. Run the existing package-manifest verifier before target mutation.
4. Install or update the managed runtime under `%LOCALAPPDATA%\QuantumLocalProduction`.
5. Preserve `config`, `data` and `output`.
6. Verify Python 3.12+ and required installed files.
7. Reuse the first valid existing configuration.
8. If no valid configuration exists, run the interactive configurator and create `ADMISSION_ONLY` configuration without finance defaults.
9. Start the reviewed import workflow in the same console.
10. Open the verified dashboard/output directory only when it is inside the managed HOME_LOCAL root.

## Repeated-run sequence

The installer creates:

- `%LOCALAPPDATA%\QuantumLocalProduction\START_QUANTUM.cmd`;
- a best-effort desktop shortcut named `Quantum HOME_LOCAL`.

The installed launcher invokes the same orchestrator with `-SkipInstall`. It reuses the installed runtime and a ready configuration, then starts a new local report selection/import.

## Preserved security gates

The one-click flow does not weaken any data-processing gate.

- Microsoft Defender scan remains enabled by default.
- `-SkipDefenderScan` is forwarded only after an explicit operator switch.
- `AUTHORIZE` remains required unless `-AuthorityAttested` was explicitly supplied in non-interactive mode.
- `REVIEWED` remains required unless `-SchemaReviewed` was explicitly supplied in non-interactive mode.
- discovery preview and post-review file SHA-256 binding remain unchanged.
- no cost, tax, expense or finance-request value is inferred.
- marketplace writes remain disabled.
- package release state remains `RELEASE_BLOCKED`.

## Configuration behavior

The launcher searches, in order, for:

1. `config\production.local.json`;
2. `config\default-home-local.json`;
3. `config\default-production.json`.

`ADMISSION_ONLY` is accepted when `configuration_status` is `READY`. `FULL` is accepted only when an explicit non-placeholder `finance_request` exists. Invalid default configuration is copied to a timestamped backup before the first-run configurator writes a replacement.

## Result behavior

The orchestrator supplies an explicit timestamped result path under `output`, then reads the completed report. When `output_bundle.directory` is inside the managed HOME_LOCAL root, the launcher opens `dashboard.html` and the output directory. An external or escaped output path is never opened automatically.

## Package contract

The Windows package now contains:

- `START_QUANTUM.cmd` — primary user action;
- `scripts\one_click_home_local.ps1` — orchestrator;
- legacy recovery commands;
- package manifest covering the new launcher and orchestrator.

The installed target contains the same one-click launcher and script. Package version is `R3_ONE_CLICK`.

## Non-interactive support

The orchestrator supports automation parameters for controlled tests and repeatable pilot runs. Non-interactive mode requires an explicit XLSX file. Configuration values and both attestations must be supplied explicitly; they are never fabricated by the launcher.

## Limitations

- The assistant cannot click or install software on the user's physical computer; the verified package must be extracted and `START_QUANTUM.cmd` must be launched locally.
- The first run still requires user-entered reporting period/retention/source identifier when no ready config exists.
- Lawful-authority and schema-review confirmations remain deliberate human decisions.
- `ADMISSION_ONLY` does not enable full finance calculation. A complete reviewed finance profile is still required for `FULL` mode.
