# Quantum WB release notes

Status: NOT_READY

Required release gate:

1. Existing Quantum repository only.
2. Branch `fix/quantum-one-click-stable-release`.
3. Windows executable or installer artifact.
4. Windows CI builds the executable or installer.
5. Windows CI launches the packaged output.
6. Health smoke-test passes from the packaged output.
7. Downloaded artifact is inspected before user delivery.
8. No service files are presented as the user-facing result.
9. Marketplace writes remain disabled.

Current blocker:

Attempts to add the Windows executable CI gate were blocked by the available tool safety layer. This is not a READY state.
