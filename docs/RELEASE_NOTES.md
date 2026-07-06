# Release Notes

Status: DEGRADED

Date: 2026-07-06

This branch now contains a verified local-pilot one-click candidate.

Added runtime behavior:

- Local browser UI at `/local-pilot`.
- Local-pilot health endpoint.
- Upload endpoint for CSV/XLSX/XLS files.
- SHA-256 receipt generation and duplicate detection.
- Decimal unit calculation with explicit required fields and no hidden defaults.
- Local Windows launcher: `scripts/Quantum_ONE_CLICK_STABLE_RELEASE.cmd`.
- Package builder and GitHub Actions package artifact.

Verified checks:

- Foundation CI: success.
- OSS Admission CI: success.
- Local Pilot Package workflow: success.
- Independent downloaded-package smoke: success.

Final release status is DEGRADED, not READY, because this is a local-pilot candidate and not a full production marketplace release.
