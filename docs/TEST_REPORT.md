# Test Report

Status: DEGRADED

Date: 2026-07-06

Head commit: `efb369fa1dfa541bcd1cc6a9ccfd4db5fd192d6b`

Verified CI results:

- Foundation CI: success.
- OSS Admission CI: success.
- Local Pilot Package: success.
- Local Pilot Package job ran `PYTHONPATH=src python3 -m quantum.scripts.ci` and `PYTHONPATH=src python3 scripts/build_local_pilot_package.py`.
- The prior manifest-only failure was corrected by updating the artifact-manifest overlay with exact diagnostics.

Test scope added in this branch:

- Decimal calculation blocks missing required fields.
- Decimal calculation uses explicit inputs and no hidden defaults.
- Upload receipt and duplicate detection.
- HTTP smoke for local-pilot health, upload and calculation.
- Package builder creates a one-click ZIP with launcher and local-pilot runtime files.

READY remains blocked for production release scope. The current verified output is a local-pilot one-click candidate.
