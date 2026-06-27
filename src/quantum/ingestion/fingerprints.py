from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping


def _sha256_json(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def structural_fingerprint(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        reader = csv.reader(handle, dialect)
        headers = next(reader)

    descriptor = {
        "format": "csv",
        "encoding": "utf-8-sig",
        "delimiter": dialect.delimiter,
        "quotechar": dialect.quotechar,
        "headers": headers,
        "column_count": len(headers),
    }
    return {"descriptor": descriptor, "sha256": _sha256_json(descriptor)}


def _infer_scalar_type(value: str) -> str:
    value = value.strip()
    if value == "":
        return "empty"
    if value.lower() in {"true", "false"}:
        return "boolean"
    try:
        int(value)
        return "integer"
    except ValueError:
        pass
    try:
        Decimal(value)
        return "decimal"
    except InvalidOperation:
        pass
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return "datetime"
    except ValueError:
        return "string"


def semantic_fingerprint(rows: Iterable[Mapping[str, str]]) -> dict[str, object]:
    column_types: dict[str, set[str]] = defaultdict(set)
    enum_samples: dict[str, set[str]] = defaultdict(set)
    row_count = 0

    for row in rows:
        row_count += 1
        for key, value in row.items():
            column_types[key].add(_infer_scalar_type(value))
            if key in {"operation_type", "currency"} and value:
                enum_samples[key].add(value)

    descriptor = {
        "column_types": {
            key: sorted(values)
            for key, values in sorted(column_types.items())
        },
        "enum_samples": {
            key: sorted(values)
            for key, values in sorted(enum_samples.items())
        },
        "row_count": row_count,
    }
    return {"descriptor": descriptor, "sha256": _sha256_json(descriptor)}
