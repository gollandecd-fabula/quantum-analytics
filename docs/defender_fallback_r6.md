# Defender-unavailable structural fallback R6

Purpose: prevent HOME_LOCAL imports from dead-ending when Microsoft Defender command-line scanning is unavailable on the local Windows host.

This does not disable Defender and does not treat detected threats as clean.

Behavior:
- If MpCmdRun succeeds, the scan outcome remains CLEAN.
- If MpCmdRun is missing or fails with service-unavailable signatures such as 0x800106BA, Quantum records DEFENDER_UNAVAILABLE_STRUCTURAL_FALLBACK.
- The file still passes through Quantum universal structural intake before XLSX routing.
- Active content, executable payloads, corrupted archives, unsafe ZIP members and external relationships remain blocked by the universal intake policy.
- If Defender returns an unrecognized non-zero result, the import still fails closed.

Known local blocker covered:
- WinDefend stopped/manual and WdNisSvc stopped/manual.
- MpCmdRun exit code 2 with 0x800106BA even for harmless probe files.
