# Migration Discipline

- Applied migrations are immutable.
- Use expand-contract for incompatible changes.
- Every migration requires preflight, backup checkpoint, rollback plan, and rehearsal.
- A migration filename is ordered and never reused.
- Destructive operations are forbidden in Foundation.
- `0001_foundation.sql` defines contracts only; it has not been applied to a database.
