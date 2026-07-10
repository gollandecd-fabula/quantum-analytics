# Local Pilot Orchestrator R21

Status: INTERNAL PILOT CANDIDATE / RELEASE_BLOCKED

R21 closes two R20 audit gaps:

1. B2 calculated totals are now constructed inside the orchestrator only from explicit finance-result bindings. An arbitrary snapshot callback is no longer accepted.
2. Admission lifecycle handling is state-aware and idempotently reuses an already admitted record after a downstream failure.

Additional controls validate source identity before finance execution, finance labels before sorting, calculation timestamps inside the admitted execution window, immutable payload hash/size, and typed aggregation across multiple finance results.

Only synthetic fixtures are committed. Marketplace writes, public hosting, production credentials and production release remain disabled.
