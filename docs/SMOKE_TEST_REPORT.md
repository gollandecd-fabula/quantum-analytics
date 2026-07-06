# Smoke Test Report

Status: DEGRADED

Date: 2026-07-06

Verified artifact class:

- Workflow: Local Pilot Package.
- Artifact name: `quantum-local-pilot-one-click`.
- The workflow builds `dist/quantum-local-pilot-one-click.zip` and uploads it with its summary file.
- Exact artifact IDs and SHA-256 values are intentionally not embedded in this tracked document because they change after documentation updates.

Smoke scope:

- Local-pilot health endpoint returns `ok`.
- Upload endpoint accepts a CSV report and creates a SHA-256 receipt.
- Calculation endpoint returns `net_profit` from explicit Decimal inputs.
- Marketplace writes remain disabled.

Independent smoke after artifact download is required before any final user-facing status.

Limitation: this is a local-pilot candidate, not a production marketplace release.
