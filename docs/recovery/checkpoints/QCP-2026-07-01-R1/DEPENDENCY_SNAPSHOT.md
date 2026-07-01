# Dependency and Runtime Snapshot

## Verified runtime evidence

- Foundation runner OS: Ubuntu 24.04 LTS.
- Python reported by the latest B1b workflow: 3.12.3.
- Repository CI requires Python 3.12 or newer.
- Foundation verification entry point: `src/quantum/scripts/ci.py`.

## Approved technology direction

Potential components are admitted only after stage need, official-registry verification, license review, and vulnerability checks:

- DuckDB
- Polars
- Pandera
- Hypothesis
- FastAPI and Pydantic
- React-admin
- ECharts

`wbsdk` requires a separate audit before admission.

## Recovery rule

Use repository lock files, workflow definitions, manifests, and official dependency-admission evidence as authoritative. Do not infer or upgrade package versions during emergency restoration.
