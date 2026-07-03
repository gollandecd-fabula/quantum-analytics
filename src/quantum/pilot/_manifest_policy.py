from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from quantum.ingestion.xlsx_inspection import (
    XlsxInspectionLimits,
    XlsxInspectionPolicy,
    XlsxSchemaExpectation,
)

from ._manifest_common import boolean, exact_keys, integer, mapping, sha256_text, text
from ._scope import LocalPilotExecutionError

_LIMIT_FIELDS = {
    "max_file_bytes",
    "max_archive_entries",
    "max_total_uncompressed_bytes",
    "max_entry_uncompressed_bytes",
    "max_compression_ratio",
    "max_xml_bytes",
    "max_rows",
    "max_columns",
}
_SCHEMA_FIELDS = {
    "schema_id",
    "schema_version",
    "schema_authority_reference",
    "direct_identifiers_expected",
    "package_kind",
    "sheet_name",
    "sheet_count",
    "header_row_index",
    "header_sha256",
    "column_count",
    "min_data_rows",
    "max_data_rows",
    "max_formula_count",
}


def _limits(value: object) -> XlsxInspectionLimits:
    item = mapping(value, "PILOT_XLSX_LIMITS_INVALID")
    exact_keys(item, _LIMIT_FIELDS, "PILOT_XLSX_LIMITS_INVALID")
    return XlsxInspectionLimits(
        **{
            field: integer(item[field], "PILOT_XLSX_LIMITS_INVALID", minimum=1)
            for field in _LIMIT_FIELDS
        }
    )


def _schema(value: object) -> XlsxSchemaExpectation:
    item = mapping(value, "PILOT_XLSX_SCHEMA_INVALID")
    exact_keys(item, _SCHEMA_FIELDS, "PILOT_XLSX_SCHEMA_INVALID")
    return XlsxSchemaExpectation(
        schema_id=text(item["schema_id"], "PILOT_XLSX_SCHEMA_INVALID"),
        schema_version=text(item["schema_version"], "PILOT_XLSX_SCHEMA_INVALID"),
        schema_authority_reference=text(
            item["schema_authority_reference"],
            "PILOT_XLSX_SCHEMA_INVALID",
        ),
        direct_identifiers_expected=boolean(
            item["direct_identifiers_expected"],
            "PILOT_XLSX_SCHEMA_INVALID",
        ),
        package_kind=text(
            item["package_kind"],
            "PILOT_XLSX_SCHEMA_INVALID",
        ),
        sheet_name=text(
            item["sheet_name"],
            "PILOT_XLSX_SCHEMA_INVALID",
            safe=False,
        ),
        sheet_count=integer(item["sheet_count"], "PILOT_XLSX_SCHEMA_INVALID", minimum=1),
        header_row_index=integer(
            item["header_row_index"],
            "PILOT_XLSX_SCHEMA_INVALID",
            minimum=1,
        ),
        header_sha256=sha256_text(
            item["header_sha256"],
            "PILOT_XLSX_SCHEMA_INVALID",
        ),
        column_count=integer(item["column_count"], "PILOT_XLSX_SCHEMA_INVALID", minimum=1),
        min_data_rows=integer(item["min_data_rows"], "PILOT_XLSX_SCHEMA_INVALID"),
        max_data_rows=integer(item["max_data_rows"], "PILOT_XLSX_SCHEMA_INVALID"),
        max_formula_count=integer(
            item["max_formula_count"],
            "PILOT_XLSX_SCHEMA_INVALID",
        ),
    )


def build_inspection_policy(value: object) -> XlsxInspectionPolicy:
    item = mapping(value, "PILOT_XLSX_POLICY_INVALID")
    exact_keys(
        item,
        {"policy_id", "version", "limits", "schemas", "prohibited_header_tokens"},
        "PILOT_XLSX_POLICY_INVALID",
    )
    schemas = item["schemas"]
    tokens = item["prohibited_header_tokens"]
    if not isinstance(schemas, list) or not schemas:
        raise LocalPilotExecutionError("PILOT_XLSX_POLICY_INVALID")
    if not isinstance(tokens, list) or any(not isinstance(token, str) for token in tokens):
        raise LocalPilotExecutionError("PILOT_XLSX_POLICY_INVALID")
    return XlsxInspectionPolicy(
        policy_id=text(item["policy_id"], "PILOT_XLSX_POLICY_INVALID"),
        version=integer(item["version"], "PILOT_XLSX_POLICY_INVALID", minimum=1),
        limits=_limits(item["limits"]),
        schemas=tuple(_schema(schema) for schema in schemas),
        prohibited_header_tokens=tuple(tokens),
    )


__all__ = ["build_inspection_policy"]
