# Test Report

Status: DEGRADED

Date: 2026-07-07

Verified CI classes:

- Foundation CI: success required.
- OSS Admission CI: success required.
- Local Pilot Package: success required.
- Local Pilot Package job runs `PYTHONPATH=src python3 -m quantum.scripts.ci` and `PYTHONPATH=src python3 scripts/build_local_pilot_package.py`.
- Manifest-only failures must be corrected only from exact CI diagnostics.

Test scope added in this branch:

- Decimal calculation blocks missing required fields.
- Decimal calculation uses explicit inputs and no hidden defaults.
- Upload receipt and duplicate detection.
- HTTP smoke for local-pilot health, upload and calculation.
- Package builder creates a one-click ZIP with launcher and local-pilot runtime files.

Final application delivery remains blocked until the dedicated release gate is complete.
