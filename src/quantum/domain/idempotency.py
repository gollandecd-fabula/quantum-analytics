from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def _digest(parts: list[str]) -> str:
    encoded = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_json_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_idempotency_key(
    *,
    organization_id: str,
    marketplace_account_id: str,
    source_file_sha256: str,
    adapter_id: str,
    adapter_version: str,
) -> str:
    return _digest([
        organization_id,
        marketplace_account_id,
        source_file_sha256,
        adapter_id,
        adapter_version,
    ])


def source_record_idempotency_key(
    *,
    import_batch_id: str,
    source_row_key: str,
    raw_row_hash: str,
) -> str:
    return _digest([import_batch_id, source_row_key, raw_row_hash])


def event_idempotency_key(
    *,
    organization_id: str,
    marketplace_account_id: str,
    event_type: str,
    stable_business_key: str,
    revision: int,
    semantic_payload_hash: str,
) -> str:
    if revision < 1:
        raise ValueError("revision must be >= 1.")
    return _digest([
        organization_id,
        marketplace_account_id,
        event_type,
        stable_business_key,
        str(revision),
        semantic_payload_hash,
    ])
