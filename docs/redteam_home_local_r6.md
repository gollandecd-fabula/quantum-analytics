# HOME_LOCAL R6 red-team blockers

Status: release candidate requires additional hardening before final publication.

Critical findings:
- Final release has not been published as a durable GitHub release asset.
- GUI confirmation is not explicit enough for the attestation boundary.
- Rejected and blocked admission states should not be grouped with partial success.
- Import execution needs timeout and cancellation behavior.
- The release candidate still needs a real or anonymized supplier-goods fixture.

Rejected implementation proposals:
1. Merge immediately because CI is green. Rejected: CI success does not resolve publication and UX/compliance blockers.
2. Keep the PR as RC and only document risks. Rejected: RC labeling would overstate readiness after red-team blockers were confirmed.
3. Publish workflow artifacts as the release. Rejected: workflow artifacts expire and are not durable release assets.
4. Treat GUI auto-attestation as acceptable because HOME_LOCAL is offline. Rejected: offline mode does not remove the need for explicit authority/schema confirmation.
5. Leave ADMISSION_REJECTED under partial status. Rejected: this creates misleading user semantics.
6. Add a synthetic supplier-goods test only. Rejected: it does not replace a real or anonymized WB fixture.

Required next actions:
- Convert the PR back to draft or blocked RC status until blockers are resolved.
- Add explicit GUI confirmation before non-interactive attestation switches are sent.
- Split UI result taxonomy into success, partial, rejected, blocked, quarantine, timeout and error.
- Add timeout and cancellation behavior for the importer process.
- Attach durable release assets only after merge and final release publication.
