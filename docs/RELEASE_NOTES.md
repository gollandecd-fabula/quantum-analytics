# Quantum WB release notes

Status: NOT_READY

Required release gate:

1. Existing Quantum repository only.
2. Branch `fix/quantum-one-click-stable-release`.
3. Final Windows application artifact.
4. Windows CI builds the final artifact.
5. Windows CI launches the packaged output.
6. Health smoke-test passes from the packaged output.
7. Downloaded artifact is inspected before user delivery.
8. No service files are presented as the user-facing result.
9. Marketplace writes remain disabled.

Current blocker:

The Windows release gate has not produced a verified final Windows application artifact. This is not a READY state.
