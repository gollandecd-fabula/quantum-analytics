# Quantum repository instructions

These instructions apply to the entire Quantum repository. ImageLab is a different project
and must never be imported into this repository's
authorization, evidence, test, workflow, state, key, or release path.

## Mandatory LarannA pre-change gate

Before changing any tracked or untracked repository file, require a new
Windows-signed Quantum authorization-only commit for the proposed transaction.
That commit must be the direct child of the work order's exact base head and
must contain only the four paths listed in
`authorization_commit_paths` inside
`docs/evidence/laranna_quantum/bootstrap/BOOTSTRAP_WORK_ORDER.json`.

From the clean authorization commit run:

```text
python tools/laranna_quantum_verifier_gate.py preflight --root . --head HEAD
```

Do not edit when the command is unavailable, exits nonzero, reports a dirty
worktree, an expired or invalid signature, a wrong head, a wrong project, an
out-of-scope path, or any release/merge/ruleset authority escalation.

After the bounded implementation commit run:

```text
python tools/laranna_quantum_verifier_gate.py verify-implementation --root . --head HEAD
PYTHONPATH=src python -m unittest tests.test_m9_maximum_assurance_control_plane -v
PYTHONPATH=src python -m quantum.scripts.ci
```

The Windows Quantum verifier must sign the exact L2 result before the final
receipt-only commit. The final commit may contain only `receipt_commit_paths`.
Validate it with:

```text
python tools/laranna_quantum_verifier_gate.py verify-final --root . --head HEAD
```

## Fail-closed boundary

- Preserve `tools/m9_maximum_assurance_control_plane.py` and Protocol v3.1 as
  the only Quantum control authority.
- Never treat a normal change receipt as merge, ruleset, pilot, marketplace
  write, deployment, or release authorization.
- Never squash, reorder, merge into, or append to the three-commit transaction.
- Stop on any missing mandatory test, evidence artifact, exact-head binding, or
  manifest mismatch.
