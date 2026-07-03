# Local Pilot Orchestrator R25

Status: INTERNAL PILOT CANDIDATE / RELEASE_BLOCKED

R25 canonicalizes dataset UUIDs before comparing source snapshots with admitted records. UUID spelling differences such as uppercase hexadecimal no longer block a valid, idempotently admitted dataset. Invalid identifiers still fail closed with the stable source-identity error. A synthetic regression covers uppercase UUID admission and reconciliation. Production release remains blocked.
