# P16 R5 Functional-Only Diagnostic

This temporary diagnostic branch is based on exact PR #49 head `16420bef3997938fdf4530c7a1c9432228bed753`.

The CI runner preserves compileall and forbidden-marker scanning, and runs every `test_*.py` module except the two artifact-manifest equality modules:

- `test_a0_manifest_diagnostic.py`
- `test_b1a_artifact_manifest.py`

Purpose: distinguish functional regressions from artifact-manifest synchronization failures. This branch is diagnostic only, contains no commercial data, and must never be merged.

`RELEASE_BLOCKED`
