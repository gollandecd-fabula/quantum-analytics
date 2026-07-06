# User Install Guide

Status: DEGRADED

Date: 2026-07-06

This branch produces a verified local-pilot one-click package artifact.

Package artifact:

- Workflow: Local Pilot Package.
- Artifact name: `quantum-local-pilot-one-click`.
- Download the latest successful artifact for the exact PR head.
- Verify the artifact metadata from GitHub Actions before user delivery.

Windows local launch:

1. Download and extract the GitHub Actions artifact.
2. Extract `quantum-local-pilot-one-click.zip`.
3. Run `scripts/Quantum_ONE_CLICK_STABLE_RELEASE.cmd`.
4. The launcher opens `http://127.0.0.1:8080/local-pilot`.

Runtime data location:

- Default: `%USERPROFILE%\.quantum-analytics\local-pilot`.
- Override: set `QUANTUM_RUNTIME_DIR` before launching.

Current limitations:

- Local pilot only.
- Marketplace writes remain disabled.
- Uploaded reports are stored as quarantined local files with SHA-256 receipts.
- READY is not claimed for production release scope.
