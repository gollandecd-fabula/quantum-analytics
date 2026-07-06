# User Install Guide

Status: DEGRADED

Date: 2026-07-06

This branch now produces a verified local-pilot one-click package artifact.

Package artifact:

- Workflow: Local Pilot Package.
- Artifact: `quantum-local-pilot-one-click`.
- Artifact ID: `8113051714`.
- Outer artifact SHA-256: `4f6fad2d515fed9f03180191874f3938f2600dea8af2299e3cd8809ef07e8ef8`.
- Inner package SHA-256: `1b51ed30c0be1636deb0b2e55e56ca1a761d827315ad047560fd34dde28eb003`.

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
