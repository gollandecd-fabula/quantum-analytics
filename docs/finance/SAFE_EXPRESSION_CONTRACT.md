# Safe Expression Contract v1

Status: `DRAFT_FOR_B1A_REVIEW`
Risk class: `R2`
Tracking issue: `#7`

## Purpose

Safe expressions support approved derived configuration without arbitrary code.
The expression is a typed JSON abstract syntax tree. It is data, never Python,
JavaScript, SQL, shell, template code, or an interpreted string.

## Value types

- `MONEY` — decimal plus currency;
- `DECIMAL` — dimensionless decimal;
- `RATE` — dimensionless decimal rate;
- `INTEGER` — whole number;
- `BOOLEAN` — condition value.

Binary arithmetic requires compatible types and units. Currency conversion is
not implicit and is unavailable in contract v1.

## Node kinds

All examples include the metadata required by
`schemas/safe-expression.schema.json`. Currency codes shown in examples are
illustrative data, never system defaults.

### Decimal literal

```json
{
  "kind": "LITERAL",
  "value": "12.50",
  "value_type": "DECIMAL",
  "currency": null,
  "unit": "DIMENSIONLESS"
}
```

`MONEY`, `DECIMAL`, and `RATE` literal values are normalized decimal strings.
JSON floating-point numbers, `NaN`, `Infinity`, exponential notation, and
locale-formatted values are forbidden.

### Integer literal

```json
{
  "kind": "LITERAL",
  "value": "12",
  "value_type": "INTEGER",
  "currency": null,
  "unit": "ITEM"
}
```

`INTEGER` literals use normalized integer strings. Decimal points and
exponential notation are forbidden, so `"12.5"` is not an integer literal.

### Boolean literal

```json
{
  "kind": "LITERAL",
  "value": true,
  "value_type": "BOOLEAN",
  "currency": null,
  "unit": "BOOLEAN"
}
```

`BOOLEAN` literals use JSON booleans `true` or `false`. Numeric or string
substitutes such as `1`, `0`, `"true"`, or `"false"` are forbidden.

A `MONEY` literal requires an explicit ISO 4217 currency. All other literal
value types require `currency: null`. A mismatch between `value`, `value_type`,
or currency metadata is `EXPRESSION_TYPE_MISMATCH` or
`EXPRESSION_CURRENCY_MISMATCH` and fails closed.

### Variable

```json
{
  "kind": "VARIABLE",
  "name": "gross_sales_amount",
  "value_type": "MONEY",
  "currency": "EUR",
  "unit": "MONEY"
}
```

The name must exist in the explicit dependency list and approved variable
registry. Unknown or dynamically constructed names are forbidden.

### Operation

```json
{
  "kind": "OPERATION",
  "operator": "MULTIPLY",
  "value_type": "MONEY",
  "currency": "EUR",
  "unit": "MONEY",
  "arguments": [
    {
      "kind": "VARIABLE",
      "name": "gross_sales_amount",
      "value_type": "MONEY",
      "currency": "EUR",
      "unit": "MONEY"
    },
    {
      "kind": "LITERAL",
      "value": "0.10",
      "value_type": "RATE",
      "currency": null,
      "unit": "RATE"
    }
  ]
}
```

## Operator allowlist

- `ADD` — two or more compatible values;
- `SUBTRACT` — exactly two compatible values;
- `MULTIPLY` — exactly two values with an approved type combination;
- `DIVIDE` — exactly two values; denominator must be non-zero;
- `NEGATE` — exactly one numeric value;
- `ABS` — exactly one numeric value;
- `MIN` — two or more compatible values;
- `MAX` — two or more compatible values;
- `IF` — exactly three arguments: boolean condition plus equal-type true/false branches;
- `EQUAL`, `LESS_THAN`, `LESS_OR_EQUAL`, `GREATER_THAN`, `GREATER_OR_EQUAL` — exactly two compatible operands, boolean result.

The machine-readable schema enforces these arities fail-closed. Rounding is not
an expression operator. It is applied only at versioned policy application
points.

## Explicitly forbidden capabilities

- function names outside the allowlist;
- attribute or property traversal;
- dynamic indexing;
- loops, recursion, comprehensions, lambdas, reflection, imports, networking,
  filesystem access, environment access, dates from wall-clock time, randomness,
  process execution, database queries, and user-defined functions;
- string concatenation or evaluation;
- implicit type coercion;
- implicit currency conversion;
- hidden default values.

## Type rules

- `ADD`, `SUBTRACT`, `MIN`, and `MAX` require identical value types, units, and currencies.
- `MONEY × DECIMAL` and `MONEY × RATE` return `MONEY`.
- `DECIMAL × DECIMAL` returns `DECIMAL`.
- `MONEY ÷ MONEY` with identical currency returns `DECIMAL`.
- `MONEY ÷ DECIMAL` returns `MONEY`.
- `DECIMAL ÷ DECIMAL` returns `DECIMAL`.
- Other combinations are invalid unless introduced by a later contract version.
- Comparison operands must be compatible and return `BOOLEAN`.
- `IF` branches must have identical type, unit, and currency.

## Typed-state propagation

Expression evaluation is not defined in B1a, but the contract requires:

- `CONFLICT` propagates as `CONFLICT`;
- `BLOCKED` propagates as `BLOCKED` unless an approved operator-specific rule says otherwise;
- `UNAVAILABLE` propagates as `UNAVAILABLE`;
- `EMPTY` remains `EMPTY`;
- numeric zero is a valid value and participates normally;
- no operator silently replaces a non-VALID state with zero.

Contract v1 defines no coalesce or fallback operator.

## Limits

A validator enforces configurable hard limits with conservative defaults in the
security policy, not business defaults:

- maximum node count;
- maximum depth;
- maximum argument count;
- maximum dependency count;
- maximum decimal precision and scale.

Exceeding a limit produces `RULE_UNSAFE_EXPRESSION` and prevents activation.

## Canonicalization and hash

Canonical expression JSON uses:

- UTF-8;
- sorted object keys;
- no insignificant whitespace;
- normalized decimal or integer strings for numeric literals;
- JSON booleans for boolean literals;
- argument order preserved.

The SHA-256 of canonical JSON is stored in the rule and calculation profile.

## Diagnostics

- `EXPRESSION_SCHEMA_INVALID`;
- `EXPRESSION_OPERATOR_FORBIDDEN`;
- `EXPRESSION_ARITY_INVALID`;
- `EXPRESSION_TYPE_MISMATCH`;
- `EXPRESSION_UNIT_MISMATCH`;
- `EXPRESSION_CURRENCY_MISMATCH`;
- `EXPRESSION_VARIABLE_UNKNOWN`;
- `EXPRESSION_DEPENDENCY_UNDECLARED`;
- `EXPRESSION_LIMIT_EXCEEDED`;
- `EXPRESSION_DIVISION_BY_ZERO_STATIC`;
- `EXPRESSION_NON_FINITE_LITERAL`.

## Gate

B1a defines and validates the expression contract only. Expression evaluation
inside the financial calculation kernel is B1b R3 work and is not authorized.
