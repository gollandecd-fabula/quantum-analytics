# Repository Recovery Map

| Area | Canonical path | Role |
|---|---|---|
| Current state | `docs/governance/CURRENT_STATE.md` | Human-readable live summary |
| Stage B live state | `docs/evidence/STAGE_B_EXECUTION_STATE.yaml` | Machine-readable unit state |
| Stage B contract | `docs/stage-contracts/STAGE-B-BUILD-v1.md` | Immutable stage authority |
| B1b execution | `docs/evidence/STAGE_B_B1B_EXECUTION_STATE.yaml` | WIP unit evidence |
| B1b manifest | `docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B1B.json` | Exact content and size integrity |
| B1b contract | `docs/finance/B1B_CALCULATION_KERNEL_CONTRACT.md` | Financial-kernel contract |
| Schemas | `schemas/` | Machine-readable contracts |
| Finance runtime | `src/quantum/finance/` | Decimal kernel, rule resolution, oracle |
| Tests | `tests/` | Contract, regression, differential, and governance tests |
| CI entry point | `src/quantum/scripts/ci.py` | Foundation verification |
| Workflows | `.github/workflows/` | Foundation and OSS Admission automation |
| Recovery package | `docs/recovery/checkpoints/` | Emergency restore index |
