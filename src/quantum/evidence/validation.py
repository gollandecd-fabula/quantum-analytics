from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Iterable, Mapping

_HEX64 = set("0123456789abcdef")


def _canonical_bytes(document: Mapping[str, Any], excluded_top_level: Iterable[str] = ()) -> bytes:
    excluded = set(excluded_top_level)
    payload = {key: value for key, value in document.items() if key not in excluded}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(document: Mapping[str, Any], excluded_top_level: Iterable[str] = ()) -> str:
    return hashlib.sha256(_canonical_bytes(document, excluded_top_level)).hexdigest()


def evidence_input_fingerprint(chain: Mapping[str, Any]) -> str:
    recorded = {
        "metric_definition_ref": chain["metric_definition_ref"],
        "calculation_profile_ref": chain["calculation_profile_ref"],
        "rounding_policy_ref": chain["rounding_policy_ref"],
        "source_authority_ref": chain["source_authority_ref"],
        "source_files": sorted(chain["source_files"], key=lambda item: item["source_file_id"]),
        "source_records": sorted(chain["source_records"], key=lambda item: item["source_record_id"]),
        "events": sorted(chain["events"], key=lambda item: item["event_id"]),
        "transformations": sorted(chain["transformations"], key=lambda item: item["transformation_id"]),
    }
    return canonical_sha256(recorded)


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


def _index(items: object, key: str, prefix: str, errors: list[str]) -> dict[str, Mapping[str, Any]]:
    if not isinstance(items, list):
        errors.append(f"{prefix}_COLLECTION_INVALID")
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        if not isinstance(item, Mapping):
            errors.append(f"{prefix}_ITEM_INVALID")
            continue
        identity = item.get(key)
        if not isinstance(identity, str) or not identity:
            errors.append(f"{prefix}_MISSING_ID")
        elif identity in result:
            errors.append(f"{prefix}_DUPLICATE_ID:{identity}")
        else:
            result[identity] = item
    return result


def validate_metric_evidence(result: Mapping[str, Any], chain: Mapping[str, Any]) -> tuple[str, ...]:
    """Return sorted fail-closed diagnostics; an empty tuple means valid evidence."""

    errors: list[str] = []

    if result.get("metric_result_id") != chain.get("metric_result_id"):
        errors.append("RESULT_CHAIN_ID_MISMATCH")
    if result.get("result_hash") != chain.get("metric_result_hash"):
        errors.append("RESULT_CHAIN_HASH_MISMATCH")

    chain_ref = result.get("evidence_chain_ref", {})
    for source, target, code in (
        (chain_ref.get("id"), chain.get("evidence_chain_id"), "EVIDENCE_CHAIN_REF_ID_MISMATCH"),
        (chain_ref.get("version"), chain.get("version"), "EVIDENCE_CHAIN_REF_VERSION_MISMATCH"),
        (chain_ref.get("content_hash"), chain.get("content_hash"), "EVIDENCE_CHAIN_REF_HASH_MISMATCH"),
    ):
        if source != target:
            errors.append(code)

    for field in ("metric_definition_ref", "calculation_profile_ref", "rounding_policy_ref", "source_authority_ref"):
        if result.get(field) != chain.get(field):
            errors.append(f"{field.upper()}_MISMATCH")

    if not _is_hash(result.get("result_hash")) or result.get("result_hash") != canonical_sha256(result, {"result_hash"}):
        errors.append("RESULT_CONTENT_HASH_MISMATCH")
    if not _is_hash(chain.get("content_hash")) or chain.get("content_hash") != canonical_sha256(
        chain, {"content_hash", "metric_result_hash"}
    ):
        errors.append("EVIDENCE_CONTENT_HASH_MISMATCH")

    fingerprint = evidence_input_fingerprint(chain)
    if chain.get("input_fingerprint") != fingerprint:
        errors.append("CHAIN_INPUT_FINGERPRINT_MISMATCH")
    if result.get("input_fingerprint") != fingerprint:
        errors.append("RESULT_INPUT_FINGERPRINT_MISMATCH")

    audit = result.get("recalculation", {})
    if not isinstance(audit, Mapping):
        audit = {}
        errors.append("RECALC_AUDIT_INVALID")
    if audit.get("replay_key") != chain.get("replay_key"):
        errors.append("REPLAY_KEY_MISMATCH")
    if audit.get("actor") != chain.get("actor"):
        errors.append("RECALC_ACTOR_MISMATCH")
    if not audit.get("actor") or not audit.get("reason"):
        errors.append("RECALC_AUDIT_INCOMPLETE")
    requested = _parse_time(audit.get("requested_at"), "RECALC_REQUESTED_AT_INVALID", errors)
    completed = _parse_time(audit.get("completed_at"), "RECALC_COMPLETED_AT_INVALID", errors)
    if requested and completed and requested > completed:
        errors.append("RECALC_TIMESTAMP_INVERSION")
    predecessor = bool(audit.get("predecessor_result_id") and audit.get("predecessor_result_hash"))
    if audit.get("kind") == "INITIAL" and (audit.get("predecessor_result_id") is not None or audit.get("predecessor_result_hash") is not None):
        errors.append("INITIAL_PREDECESSOR_PRESENT")
    if audit.get("kind") in {"RECALCULATION", "RESTATEMENT"} and not predecessor:
        errors.append("RECALC_PREDECESSOR_MISSING")

    typed = result.get("result", {})
    validity = result.get("validity", {})
    if not isinstance(typed, Mapping) or not isinstance(validity, Mapping):
        errors.append("RESULT_STATE_METADATA_INVALID")
        typed, validity = {}, {}
    state = typed.get("state")
    if validity.get("state") != state:
        errors.append("VALIDITY_STATE_MISMATCH")
    if state == "VALID":
        if typed.get("value") is None or typed.get("reason_code") is not None:
            errors.append("VALID_RESULT_VALUE_CONTRADICTION")
    else:
        if typed.get("value") is not None or not typed.get("reason_code"):
            errors.append("NON_VALID_RESULT_VALUE_CONTRADICTION")
        if validity.get("publishable") is not False:
            errors.append("NON_VALID_RESULT_PUBLISHABLE")

    if result.get("mode") == "ACTUAL" and result.get("scenario_id") is not None:
        errors.append("ACTUAL_SCENARIO_ID_PRESENT")
    if result.get("mode") == "SCENARIO" and not result.get("scenario_id"):
        errors.append("SCENARIO_ID_MISSING")

    period = result.get("period", {})
    if not isinstance(period, Mapping):
        period = {}
        errors.append("PERIOD_INVALID")
    start = _parse_time(period.get("start"), "PERIOD_START_INVALID", errors)
    end = _parse_time(period.get("end"), "PERIOD_END_INVALID", errors)
    if start and end and start >= end:
        errors.append("PERIOD_NOT_INCREASING")

    freshness = result.get("freshness", {})
    if not isinstance(freshness, Mapping):
        freshness = {}
        errors.append("FRESHNESS_INVALID")
    as_of = _parse_time(freshness.get("as_of"), "FRESHNESS_AS_OF_INVALID", errors)
    evaluated = _parse_time(freshness.get("evaluated_at"), "FRESHNESS_EVALUATED_AT_INVALID", errors)
    if as_of and evaluated and as_of > evaluated:
        errors.append("FRESHNESS_TIMESTAMP_INVERSION")
    status, age, maximum = freshness.get("status"), freshness.get("age_seconds"), freshness.get("max_age_seconds")
    if status == "FRESH" and (not isinstance(age, int) or not isinstance(maximum, int) or age > maximum):
        errors.append("FRESHNESS_FRESH_CONTRADICTION")
    if status == "STALE" and (not isinstance(age, int) or not isinstance(maximum, int) or age <= maximum):
        errors.append("FRESHNESS_STALE_CONTRADICTION")
    if status == "UNKNOWN" and (age is not None or maximum is not None):
        errors.append("FRESHNESS_UNKNOWN_CONTRADICTION")

    files = _index(chain.get("source_files"), "source_file_id", "SOURCE_FILE", errors)
    records = _index(chain.get("source_records"), "source_record_id", "SOURCE_RECORD", errors)
    events = _index(chain.get("events"), "event_id", "EVENT", errors)
    transformations = _index(chain.get("transformations"), "transformation_id", "TRANSFORMATION", errors)

    files_by_hash: dict[str, str] = {}
    for file_id, item in files.items():
        digest = item.get("sha256")
        if not _is_hash(digest):
            errors.append(f"SOURCE_FILE_HASH_INVALID:{file_id}")
        elif digest in files_by_hash and files_by_hash[digest] != file_id:
            errors.append(f"SOURCE_FILE_HASH_DUPLICATE:{digest}")
        else:
            files_by_hash[str(digest)] = file_id

    for record_id, item in records.items():
        if item.get("source_file_sha256") not in files_by_hash:
            errors.append(f"SOURCE_RECORD_FILE_MISSING:{record_id}")
        if not _is_hash(item.get("raw_row_hash")):
            errors.append(f"SOURCE_RECORD_HASH_INVALID:{record_id}")

    for event_id, item in events.items():
        record = records.get(str(item.get("source_record_id")))
        if record is None:
            errors.append(f"EVENT_RECORD_MISSING:{event_id}")
        elif item.get("source_file_sha256") != record.get("source_file_sha256"):
            errors.append(f"EVENT_RECORD_FILE_MISMATCH:{event_id}")
        if item.get("source_file_sha256") not in files_by_hash:
            errors.append(f"EVENT_FILE_MISSING:{event_id}")

    identities = {
        "METRIC_RESULT": {str(result.get("metric_result_id"))},
        "METRIC_DEFINITION": {str(chain.get("metric_definition_ref", {}).get("id"))},
        "CALCULATION_PROFILE": {str(chain.get("calculation_profile_ref", {}).get("id"))},
        "ROUNDING_POLICY": {str(chain.get("rounding_policy_ref", {}).get("id"))},
        "SOURCE_AUTHORITY": {str(chain.get("source_authority_ref", {}).get("id"))},
        "SOURCE_FILE": set(files), "SOURCE_RECORD": set(records),
        "EVENT": set(events), "TRANSFORMATION": set(transformations),
    }
    observed: set[tuple[str, str, str, str, str]] = set()
    links = chain.get("links", [])
    if not isinstance(links, list):
        links = []
        errors.append("LINK_COLLECTION_INVALID")
    for item in links:
        if not isinstance(item, Mapping):
            errors.append("LINK_ITEM_INVALID")
            continue
        edge = tuple(str(item.get(key)) for key in ("from_kind", "from_id", "to_kind", "to_id", "relation"))
        if edge in observed:
            errors.append("DUPLICATE_LINK:" + "|".join(edge))
        observed.add(edge)
        if edge[1] not in identities.get(edge[0], set()):
            errors.append(f"LINK_FROM_MISSING:{edge[0]}:{edge[1]}")
        if edge[3] not in identities.get(edge[2], set()):
            errors.append(f"LINK_TO_MISSING:{edge[2]}:{edge[3]}")

    result_id = str(result.get("metric_result_id"))
    required = {
        ("METRIC_DEFINITION", str(chain.get("metric_definition_ref", {}).get("id")), "DEFINED_BY"),
        ("CALCULATION_PROFILE", str(chain.get("calculation_profile_ref", {}).get("id")), "CALCULATED_WITH"),
        ("ROUNDING_POLICY", str(chain.get("rounding_policy_ref", {}).get("id")), "ROUNDED_WITH"),
        ("SOURCE_AUTHORITY", str(chain.get("source_authority_ref", {}).get("id")), "AUTHORIZED_BY"),
    }
    actual = {
        (to_kind, to_id, relation)
        for from_kind, from_id, to_kind, to_id, relation in observed
        if from_kind == "METRIC_RESULT" and from_id == result_id
    }
    for missing in sorted(required - actual):
        errors.append("REQUIRED_RESULT_LINK_MISSING:" + "|".join(missing))

    linked_transformations: set[str] = set()
    for event_id, event in events.items():
        record_id = str(event.get("source_record_id"))
        result_event_edge = ("METRIC_RESULT", result_id, "EVENT", event_id, "DERIVED_FROM")
        if result_event_edge not in observed:
            errors.append(f"REQUIRED_RESULT_EVENT_LINK_MISSING:{event_id}")

        event_record_edge = ("EVENT", event_id, "SOURCE_RECORD", record_id, "NORMALIZED_FROM")
        if event_record_edge not in observed:
            errors.append(f"REQUIRED_EVENT_RECORD_LINK_MISSING:{event_id}:{record_id}")

        event_transforms = {
            to_id
            for from_kind, from_id, to_kind, to_id, relation in observed
            if from_kind == "EVENT"
            and from_id == event_id
            and to_kind == "TRANSFORMATION"
            and relation == "TRANSFORMED_BY"
        }
        if not event_transforms:
            errors.append(f"REQUIRED_EVENT_TRANSFORMATION_LINK_MISSING:{event_id}")
        linked_transformations.update(event_transforms)

    for record_id, record in records.items():
        file_id = files_by_hash.get(str(record.get("source_file_sha256")))
        if file_id is not None:
            edge = ("SOURCE_RECORD", record_id, "SOURCE_FILE", file_id, "INGESTED_FROM")
            if edge not in observed:
                errors.append(f"REQUIRED_RECORD_FILE_LINK_MISSING:{record_id}:{file_id}")

    for transformation_id in transformations:
        if transformation_id not in linked_transformations:
            errors.append(f"ORPHAN_TRANSFORMATION:{transformation_id}")

    return tuple(sorted(set(errors)))
