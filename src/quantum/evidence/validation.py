from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable, Mapping


_HEX64 = set("0123456789abcdef")


def _canonical_bytes(document: Mapping[str, Any], excluded_top_level: Iterable[str] = ()) -> bytes:
    excluded = set(excluded_top_level)
    payload = {key: value for key, value in document.items() if key not in excluded}
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(document: Mapping[str, Any], excluded_top_level: Iterable[str] = ()) -> str:
    return hashlib.sha256(_canonical_bytes(document, excluded_top_level)).hexdigest()


def evidence_input_fingerprint(chain: Mapping[str, Any]) -> str:
    recorded_inputs = {
        "metric_definition_ref": chain["metric_definition_ref"],
        "calculation_profile_ref": chain["calculation_profile_ref"],
        "rounding_policy_ref": chain["rounding_policy_ref"],
        "source_authority_ref": chain["source_authority_ref"],
        "source_files": sorted(chain["source_files"], key=lambda item: item["source_file_id"]),
        "source_records": sorted(chain["source_records"], key=lambda item: item["source_record_id"]),
        "events": sorted(chain["events"], key=lambda item: item["event_id"]),
        "transformations": sorted(chain["transformations"], key=lambda item: item["transformation_id"]),
    }
    return canonical_sha256(recorded_inputs)


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX64


def _parse_time(value: object, code: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(code)
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(code)
        return None


def _unique_by(items: list[Mapping[str, Any]], key: str, code: str, errors: list[str]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for item in items:
        identity = item.get(key)
        if not isinstance(identity, str) or not identity:
            errors.append(f"{code}_MISSING_ID")
            continue
        if identity in index:
            errors.append(f"{code}_DUPLICATE_ID:{identity}")
            continue
        index[identity] = item
    return index


def validate_metric_evidence(result: Mapping[str, Any], chain: Mapping[str, Any]) -> tuple[str, ...]:
    """Return deterministic fail-closed diagnostic codes; an empty tuple is valid."""

    errors: list[str] = []

    if result.get("metric_result_id") != chain.get("metric_result_id"):
        errors.append("RESULT_CHAIN_ID_MISMATCH")
    if result.get("result_hash") != chain.get("metric_result_hash"):
        errors.append("RESULT_CHAIN_HASH_MISMATCH")

    evidence_ref = result.get("evidence_chain_ref", {})
    if evidence_ref.get("id") != chain.get("evidence_chain_id"):
        errors.append("EVIDENCE_CHAIN_REF_ID_MISMATCH")
    if evidence_ref.get("version") != chain.get("version"):
        errors.append("EVIDENCE_CHAIN_REF_VERSION_MISMATCH")
    if evidence_ref.get("content_hash") != chain.get("content_hash"):
        errors.append("EVIDENCE_CHAIN_REF_HASH_MISMATCH")

    for field in (
        "metric_definition_ref",
        "calculation_profile_ref",
        "rounding_policy_ref",
        "source_authority_ref",
    ):
        if result.get(field) != chain.get(field):
            errors.append(f"{field.upper()}_MISMATCH")

    if not _is_hash(result.get("result_hash")) or result.get("result_hash") != canonical_sha256(result, {"result_hash"}):
        errors.append("RESULT_CONTENT_HASH_MISMATCH")
    if not _is_hash(chain.get("content_hash")) or chain.get("content_hash") != canonical_sha256(chain, {"content_hash"}):
        errors.append("EVIDENCE_CONTENT_HASH_MISMATCH")

    expected_fingerprint = evidence_input_fingerprint(chain)
    if chain.get("input_fingerprint") != expected_fingerprint:
        errors.append("CHAIN_INPUT_FINGERPRINT_MISMATCH")
    if result.get("input_fingerprint") != expected_fingerprint:
        errors.append("RESULT_INPUT_FINGERPRINT_MISMATCH")
    audit = result.get("recalculation", {})
    if audit.get("replay_key") != chain.get("replay_key"):
        errors.append("REPLAY_KEY_MISMATCH")

    typed_result = result.get("result", {})
    result_state = typed_result.get("state")
    validity = result.get("validity", {})
    if validity.get("state") != result_state:
        errors.append("VALIDITY_STATE_MISMATCH")
    if result_state == "VALID":
        if typed_result.get("value") is None or typed_result.get("reason_code") is not None:
            errors.append("VALID_RESULT_VALUE_CONTRADICTION")
    else:
        if typed_result.get("value") is not None or not typed_result.get("reason_code"):
            errors.append("NON_VALID_RESULT_VALUE_CONTRADICTION")
        if validity.get("publishable") is not False:
            errors.append("NON_VALID_RESULT_PUBLISHABLE")

    mode = result.get("mode")
    scenario_id = result.get("scenario_id")
    if mode == "ACTUAL" and scenario_id is not None:
        errors.append("ACTUAL_SCENARIO_ID_PRESENT")
    if mode == "SCENARIO" and not scenario_id:
        errors.append("SCENARIO_ID_MISSING")

    period = result.get("period", {})
    period_start = _parse_time(period.get("start"), "PERIOD_START_INVALID", errors)
    period_end = _parse_time(period.get("end"), "PERIOD_END_INVALID", errors)
    if period_start and period_end and period_start >= period_end:
        errors.append("PERIOD_NOT_INCREASING")

    requested = _parse_time(audit.get("requested_at"), "RECALC_REQUESTED_AT_INVALID", errors)
    completed = _parse_time(audit.get("completed_at"), "RECALC_COMPLETED_AT_INVALID", errors)
    if requested and completed and requested > completed:
        errors.append("RECALC_TIMESTAMP_INVERSION")
    kind = audit.get("kind")
    predecessor_present = bool(audit.get("predecessor_result_id") and audit.get("predecessor_result_hash"))
    if kind == "INITIAL" and (audit.get("predecessor_result_id") is not None or audit.get("predecessor_result_hash") is not None):
        errors.append("INITIAL_PREDECESSOR_PRESENT")
    if kind in {"RECALCULATION", "RESTATEMENT"} and not predecessor_present:
        errors.append("RECALC_PREDECESSOR_MISSING")
    if not audit.get("actor") or not audit.get("reason"):
        errors.append("RECALC_AUDIT_INCOMPLETE")

    freshness = result.get("freshness", {})
    as_of = _parse_time(freshness.get("as_of"), "FRESHNESS_AS_OF_INVALID", errors)
    evaluated = _parse_time(freshness.get("evaluated_at"), "FRESHNESS_EVALUATED_AT_INVALID", errors)
    if as_of and evaluated and as_of > evaluated:
        errors.append("FRESHNESS_TIMESTAMP_INVERSION")
    freshness_status = freshness.get("status")
    age = freshness.get("age_seconds")
    maximum = freshness.get("max_age_seconds")
    if freshness_status == "FRESH" and (not isinstance(age, int) or not isinstance(maximum, int) or age > maximum):
        errors.append("FRESHNESS_FRESH_CONTRADICTION")
    if freshness_status == "STALE" and (not isinstance(age, int) or not isinstance(maximum, int) or age <= maximum):
        errors.append("FRESHNESS_STALE_CONTRADICTION")
    if freshness_status == "UNKNOWN" and (age is not None or maximum is not None):
        errors.append("FRESHNESS_UNKNOWN_CONTRADICTION")

    files = _unique_by(list(chain.get("source_files", [])), "source_file_id", "SOURCE_FILE", errors)
    records = _unique_by(list(chain.get("source_records", [])), "source_record_id", "SOURCE_RECORD", errors)
    events = _unique_by(list(chain.get("events", [])), "event_id", "EVENT", errors)
    transformations = _unique_by(list(chain.get("transformations", [])), "transformation_id", "TRANSFORMATION", errors)

    files_by_hash: dict[str, str] = {}
    for file_id, file_item in files.items():
        digest = file_item.get("sha256")
        if not _is_hash(digest):
            errors.append(f"SOURCE_FILE_HASH_INVALID:{file_id}")
            continue
        if digest in files_by_hash and files_by_hash[digest] != file_id:
            errors.append(f"SOURCE_FILE_HASH_DUPLICATE:{digest}")
        files_by_hash[digest] = file_id

    for record_id, record in records.items():
        if record.get("source_file_sha256") not in files_by_hash:
            errors.append(f"SOURCE_RECORD_FILE_MISSING:{record_id}")
        if not _is_hash(record.get("raw_row_hash")):
            errors.append(f"SOURCE_RECORD_HASH_INVALID:{record_id}")

    for event_id, event in events.items():
        record = records.get(str(event.get("source_record_id")))
        if record is None:
            errors.append(f"EVENT_RECORD_MISSING:{event_id}")
        elif event.get("source_file_sha256") != record.get("source_file_sha256"):
            errors.append(f"EVENT_RECORD_FILE_MISMATCH:{event_id}")
        if event.get("source_file_sha256") not in files_by_hash:
            errors.append(f"EVENT_FILE_MISSING:{event_id}")

    identities: dict[str, set[str]] = {
        "METRIC_RESULT": {str(result.get("metric_result_id"))},
        "METRIC_DEFINITION": {str(chain.get("metric_definition_ref", {}).get("id"))},
        "CALCULATION_PROFILE": {str(chain.get("calculation_profile_ref", {}).get("id"))},
        "ROUNDING_POLICY": {str(chain.get("rounding_policy_ref", {}).get("id"))},
        "SOURCE_AUTHORITY": {str(chain.get("source_authority_ref", {}).get("id"))},
        "SOURCE_FILE": set(files),
        "SOURCE_RECORD": set(records),
        "EVENT": set(events),
        "TRANSFORMATION": set(transformations),
    }
    observed_links: set[tuple[str, str, str, str, str]] = set()
    for link in chain.get("links", []):
        signature = (
            str(link.get("from_kind")), str(link.get("from_id")),
            str(link.get("to_kind")), str(link.get("to_id")), str(link.get("relation")),
        )
        if signature in observed_links:
            errors.append("DUPLICATE_LINK:" + "|".join(signature))
        observed_links.add(signature)
        if signature[1] not in identities.get(signature[0], set()):
            errors.append(f"LINK_FROM_MISSING:{signature[0]}:{signature[1]}")
        if signature[3] not in identities.get(signature[2], set()):
            errors.append(f"LINK_TO_MISSING:{signature[2]}:{signature[3]}")

    required_result_links = {
        ("METRIC_DEFINITION", str(chain.get("metric_definition_ref", {}).get("id")), "DEFINED_BY"),
        ("CALCULATION_PROFILE", str(chain.get("calculation_profile_ref", {}).get("id")), "CALCULATED_WITH"),
        ("ROUNDING_POLICY", str(chain.get("rounding_policy_ref", {}).get("id")), "ROUNDED_WITH"),
        ("SOURCE_AUTHORITY", str(chain.get("source_authority_ref", {}).get("id")), "AUTHORIZED_BY"),
    }
    actual_result_links = {
        (to_kind, to_id, relation)
        for from_kind, from_id, to_kind, to_id, relation in observed_links
        if from_kind == "METRIC_RESULT" and from_id == str(result.get("metric_result_id"))
    }
    for required in sorted(required_result_links - actual_result_links):
        errors.append("REQUIRED_RESULT_LINK_MISSING:" + "|".join(required))

    return tuple(sorted(set(errors)))
