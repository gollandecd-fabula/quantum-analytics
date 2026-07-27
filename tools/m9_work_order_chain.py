from __future__ import annotations

import copy
import fnmatch
import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

_WORK_ORDER_SIGNATURE_FIELD = "work_order_sha256"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_PRODUCT_PREFIXES = (
    "src/",
    "scripts/windows/",
    "installer/",
)


def _canonical_sha256(value: Mapping[str, Any], signature_field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(signature_field, None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_work_order_signature(work_order: Mapping[str, Any]) -> bool:
    actual = work_order.get(_WORK_ORDER_SIGNATURE_FIELD)
    if not isinstance(actual, str) or not re.fullmatch(r"[0-9a-f]{64}", actual):
        return False
    return hashlib.sha256(
        json.dumps(
            {
                key: copy.deepcopy(value)
                for key, value in work_order.items()
                if key != _WORK_ORDER_SIGNATURE_FIELD
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest() == actual


def _normalize_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.replace("\\", "/")
    path = PurePosixPath(candidate)
    if path.is_absolute() or ".." in path.parts:
        return None
    normalized = path.as_posix()
    if normalized in {"", "."}:
        return None
    return normalized


def _matches_forbidden(path: str, patterns: Sequence[Any]) -> str | None:
    for raw_pattern in patterns:
        if not isinstance(raw_pattern, str) or not raw_pattern:
            continue
        pattern = raw_pattern.replace("\\", "/")
        if fnmatch.fnmatchcase(path, pattern):
            return pattern
    return None


def _is_product_path(path: str) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in _PRODUCT_PREFIXES)


def validate_atomic_work_order_chain(
    segments: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate an ordered commit/work-order chain without making release decisions.

    Each segment is independently checked against its own signed work order.
    The function is deliberately pure: it does not read a repository, schedule
    requirements, mutate canonical RTM state, or authorize a release.
    """

    findings: list[str] = []
    normalized_for_digest: list[dict[str, Any]] = []

    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        segments = []
        findings.append("WORK_ORDER_CHAIN_INVALID_TYPE")
    if not segments:
        findings.append("WORK_ORDER_CHAIN_EMPTY")

    previous_result: str | None = None
    seen_results: set[str] = set()
    seen_work_orders: set[str] = set()

    for index, raw_segment in enumerate(segments):
        if not isinstance(raw_segment, Mapping):
            findings.append(f"WORK_ORDER_CHAIN_SEGMENT_INVALID:{index}")
            continue

        segment = dict(raw_segment)
        parent = segment.get("parent_exact_head")
        result = segment.get("result_exact_head")
        if not isinstance(parent, str) or _HEX40.fullmatch(parent) is None:
            findings.append(f"WORK_ORDER_CHAIN_PARENT_INVALID:{index}")
        if not isinstance(result, str) or _HEX40.fullmatch(result) is None:
            findings.append(f"WORK_ORDER_CHAIN_RESULT_INVALID:{index}")
        if index and previous_result is not None and parent != previous_result:
            findings.append(f"WORK_ORDER_CHAIN_PARENT_MISMATCH:{index}")
        if isinstance(result, str):
            if result in seen_results:
                findings.append(f"WORK_ORDER_CHAIN_RESULT_DUPLICATE:{index}")
            seen_results.add(result)
            previous_result = result

        work_order = segment.get("governing_work_order")
        if not isinstance(work_order, Mapping):
            findings.append(f"WORK_ORDER_MISSING:{index}")
            work_order = {}
        elif not _verify_work_order_signature(work_order):
            findings.append(f"WORK_ORDER_SIGNATURE_INVALID:{index}")

        work_order_id = work_order.get("work_order_id")
        if not isinstance(work_order_id, str) or not work_order_id:
            findings.append(f"WORK_ORDER_ID_INVALID:{index}")
        elif work_order_id in seen_work_orders:
            findings.append(f"WORK_ORDER_ID_DUPLICATE:{index}:{work_order_id}")
        else:
            seen_work_orders.add(work_order_id)

        allowed_raw = work_order.get("files_allowed_to_change", [])
        allowed = {
            normalized
            for raw in allowed_raw
            if (normalized := _normalize_path(raw)) is not None
        }
        forbidden = work_order.get("files_forbidden_to_change", [])
        product_authorized = work_order.get("product_change_authorized") is True

        changed_raw = segment.get("actual_changed_paths", [])
        if not isinstance(changed_raw, Sequence) or isinstance(changed_raw, (str, bytes)):
            changed_raw = []
            findings.append(f"WORK_ORDER_CHANGED_PATHS_INVALID:{index}")

        normalized_changed: list[str] = []
        seen_paths: set[str] = set()
        for raw_path in changed_raw:
            path = _normalize_path(raw_path)
            if path is None:
                findings.append(f"WORK_ORDER_PATH_INVALID:{index}:{raw_path}")
                continue
            if path in seen_paths:
                findings.append(f"WORK_ORDER_PATH_DUPLICATE:{index}:{path}")
                continue
            seen_paths.add(path)
            normalized_changed.append(path)

            if path not in allowed:
                findings.append(f"WORK_ORDER_SCOPE_VIOLATION:{index}:{path}")
            forbidden_pattern = _matches_forbidden(path, forbidden)
            if forbidden_pattern is not None:
                findings.append(
                    f"WORK_ORDER_FORBIDDEN_PATH:{index}:{path}:{forbidden_pattern}"
                )
            if _is_product_path(path) and not product_authorized:
                findings.append(
                    f"PRODUCT_CODE_CHANGED_WITHOUT_REQUIREMENT:{index}:{path}"
                )

        expected_raw = segment.get("expected_changed_paths")
        if expected_raw is not None:
            expected = sorted(
                normalized
                for raw in expected_raw
                if (normalized := _normalize_path(raw)) is not None
            )
            if sorted(normalized_changed) != expected:
                findings.append(f"WORK_ORDER_CHANGED_PATH_SET_MISMATCH:{index}")

        normalized_for_digest.append(
            {
                "parent_exact_head": parent,
                "result_exact_head": result,
                "actual_changed_paths": sorted(normalized_changed),
                "work_order_id": work_order_id,
                "work_order_sha256": work_order.get(_WORK_ORDER_SIGNATURE_FIELD),
            }
        )

    findings = sorted(set(findings))
    chain_sha256 = hashlib.sha256(
        json.dumps(
            normalized_for_digest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "artifact_type": "ATOMIC_WORK_ORDER_CHAIN_VALIDATION_REPORT",
        "schema_version": "1.0.0",
        "status": "PASS" if not findings else "FAIL",
        "segment_count": len(segments),
        "chain_sha256": chain_sha256,
        "findings": findings,
        "release_authorized": False,
    }
