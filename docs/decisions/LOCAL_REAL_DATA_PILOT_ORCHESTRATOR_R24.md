# Local Pilot Orchestrator R24

Status: INTERNAL PILOT CANDIDATE / RELEASE_BLOCKED

R24 binds every finance request to the actual admission decision timestamp stored in the admitted dataset record. Retry callers cannot widen the finance execution window by supplying an earlier `admitted_at` value. A synthetic regression verifies rejection of calculations that occur before the persisted admission decision. Production release remains blocked.
