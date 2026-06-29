# Quantum Supply-Chain Policy

Status: **R2 admission policy / no runtime installation**

## 1. Admission boundary

Dependency admission and dependency installation are separate gates. Admission records a
candidate, exact candidate version, intended architectural boundary, license, and review
requirements. It does not authorize installation.

## 2. Required controls before first installation

1. Verify the exact version against the official package registry.
2. Generate or update a lock file with exact versions.
3. Record distribution integrity hashes.
4. Generate an SPDX or CycloneDX SBOM for direct and transitive packages.
5. Scan exact versions against OSV or an equivalent maintained advisory database.
6. Review every transitive license against the license policy.
7. Run compatibility, contract, malformed-input, and rollback tests.
8. Record the resulting current-head CI evidence.

## 3. Update policy

- Automatic dependency upgrades are forbidden.
- Version ranges are forbidden in production lock files.
- Every upgrade requires an isolated branch, changelog review, fresh SBOM, vulnerability
  scan, regression tests, independent review, and exact-head CI.
- Pre-release versions are forbidden unless explicitly approved for a bounded experiment.

## 4. Marketplace SDK controls

Marketplace SDKs are treated as untrusted transport adapters.

- Domain services depend only on Quantum-owned ports.
- Adapters expose an explicit read-only allowlist.
- Unknown endpoints fail closed.
- Write-capable methods are absent from the Quantum port and rejected at runtime.
- Tokens are isolated, redacted from logs, and never stored in fixtures.
- Sandbox and mocked contract tests are required before any live read operation.

`wbsdk` remains `AUDIT_REQUIRED` because it is Alpha and exposes both read and write
operations.

## 5. CI controls

The OSS admission workflow uses only the Python standard library. It verifies official
registry metadata and submits an exact package/version batch to the OSV API. Any registry
mismatch, unknown license, vulnerability, malformed response, or network failure blocks
the admission check. No third-party GitHub Action is used.

## 6. Release boundary

This policy does not authorize deployment, marketplace writes, merge to `main`, or
production release. `RELEASE_BLOCKED` remains in force.
