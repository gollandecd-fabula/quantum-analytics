# Local Pilot Orchestrator R22

Status: INTERNAL PILOT CANDIDATE / RELEASE_BLOCKED

R22 requires exact boolean values for every scope control. Required controls accept only `True`. Disabled capabilities accept only `False`. Non-boolean truthy or falsey values fail before dataset admission. Synthetic regressions cover all scope flags. Production release remains blocked.
