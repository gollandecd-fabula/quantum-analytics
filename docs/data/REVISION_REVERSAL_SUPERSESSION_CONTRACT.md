# Revision, Reversal, and Supersession Contract v1.0

Status: `APPROVED_WITHIN_STAGE_A4`
Risk class: `R3`

## Terms

### Revision

A new authoritative representation of the same business event after source correction.

Requirements:

- same `stable_business_key`;
- incremented `revision`;
- `supersedes_event_id` references the previous revision;
- previous event remains immutable;
- impact report is generated for published periods.

### Reversal

A business event that economically negates another event.

Requirements:

- separate canonical event;
- `reversal_of_event_id` references the reversed event;
- reversal amount and units are explicit;
- original event is not deleted or edited;
- partial reversal is allowed and quantified.

### Supersession

A new event version replaces the previous event for current-state interpretation,
without erasing history.

## Mutual constraints

- An event cannot supersede itself.
- A reversal cannot reverse itself.
- Reversal chains must be acyclic.
- Supersession chains must be acyclic.
- Revision numbers must increase monotonically for one stable business key.
- One event may be partially reversed by multiple reversal events.
- Total reversal cannot exceed the reversible economic quantity unless the event type explicitly permits over-adjustment and reconciliation flags it.
- A restatement creates a new metric snapshot; it never mutates the published snapshot.

## Return lifecycle

```text
Sale
→ Return initiated
→ Return accepted/rejected
→ Condition determined
→ Restock / Write-off / Loss / Compensation
→ Optional resale
```

Each state transition is a separate event or explicit event revision.
Cost restoration, write-off, and compensation must be mutually reconciled.
