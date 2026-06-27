# CI Baseline

## Current executable check

```bash
PYTHONPATH=src python -m quantum.scripts.ci
```

It performs:

- Python bytecode compilation;
- forbidden secret/write-marker scan;
- standard-library unit and contract tests.

## GitHub Actions state

No active workflow is added while the dedicated repository is unavailable.

Activation requirements:

- repository is private and connected;
- branch protection is configured;
- every action is pinned to an immutable commit SHA;
- required checks are named and documented;
- workflow permissions are read-only by default;
- no production or marketplace credentials are available to CI.
