# Typed State Contract v1.0

Status: `APPROVED_WITHIN_STAGE_A4`
Risk class: `R3`
Authority: Constitution v3.0

## Purpose

Prevent silent conversion of missing, blocked, unavailable, conflicting, or invalid
business values into numeric zero or other plausible-looking values.

## Canonical states

| State | Meaning | Numeric operations | Publication |
|---|---|---|---|
| `VALID` | A value passed structural and semantic validation | Allowed | Allowed |
| `EMPTY` | Source field is present but contains no value | Forbidden | Allowed with explicit state |
| `BLOCKED` | Required dependency or approval is missing | Forbidden | Dependent result blocked |
| `UNAVAILABLE` | Source does not provide the requested value | Forbidden | Allowed with limitation |
| `CONFLICT` | Two authoritative candidates disagree beyond tolerance | Forbidden | Dependent result blocked |
| `INVALID` | Value failed validation | Forbidden | Quarantine or blocked result |
| `NOT_APPLICABLE` | Concept does not apply to this entity or event | Forbidden | Allowed with explanation |

Numeric zero is a `VALID` value whose payload is exactly zero. It is never a state.

## Canonical representation

```json
{
  "state": "VALID",
  "value": "0.00",
  "value_type": "decimal",
  "unit": "RUB",
  "reason_code": null,
  "source_record_id": "src_...",
  "observed_at": "2026-06-27T10:00:00Z"
}
```

Non-valid states must set `value` to `null`.

## Propagation rules

1. `INVALID` never participates in calculation.
2. `CONFLICT` blocks dependent calculations until resolved or an approved authority rule selects a source.
3. `BLOCKED` blocks only dependent calculations.
4. `UNAVAILABLE`, `EMPTY`, and `NOT_APPLICABLE` remain distinguishable.
5. Aggregation over mixed states must disclose excluded records and state counts.
6. A result may be `VALID` only when all mandatory dependencies are `VALID`.
7. A fallback source may convert `UNAVAILABLE` to `VALID` only through an explicit Source Authority rule.
8. Presentation layers may format values but may not collapse states.

## Invariants

- `state != VALID` implies `value == null`.
- `state == VALID` implies `value != null`.
- zero must be represented as `state=VALID`, never as `EMPTY`.
- every non-valid state requires `reason_code`.
- every published typed value records provenance or an explicit system-generated reason.
