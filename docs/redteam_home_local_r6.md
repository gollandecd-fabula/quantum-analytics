# HOME_LOCAL R6 blocker note

Status: blocked before final publication.

Findings:
- Release assets are still workflow artifacts, not durable publication assets.
- The UI import path still needs a stronger explicit confirmation boundary.
- Rejected and blocked states need clearer user-facing status labels.
- Import execution needs bounded runtime and cancellation behavior.
- Real supplier-goods coverage is still required.

Rejected options:
1. Merge only because CI is green.
2. Publish temporary workflow artifacts as final assets.
3. Keep the RC label while blockers remain.
4. Treat offline mode as enough for implicit confirmation.
5. Keep rejected states inside partial-success semantics.
6. Rely only on synthetic supplier-goods coverage.
