# Local Pilot Orchestrator R23

Status: INTERNAL PILOT CANDIDATE / RELEASE_BLOCKED

R23 performs constant-time identifier comparisons on UTF-8 bytes. Unicode tenant, account, organization, declaration and source identifiers no longer raise an untyped comparison error. Matching identifiers continue normally and mismatches return stable fail-closed pilot error codes. Synthetic regressions cover Unicode organization success and Unicode identity mismatches. Production release remains blocked.
