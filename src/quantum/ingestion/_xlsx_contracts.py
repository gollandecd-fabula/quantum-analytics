from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re
from typing import Final
import unicodedata

_HEX_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
class XlsxInspectionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _positive_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise XlsxInspectionError(code)
    return value


def _safe_text(value: object, code: str, *, max_length: int = 160) -> str:
    if not isinstance(value, str):
        raise XlsxInspectionError(code)
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise XlsxInspectionError(code)
    return normalized


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _normalized_header(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).strip().split())


def normalized_header_sha256(headers: tuple[str, ...] | list[str]) -> str:
    if not isinstance(headers, (tuple, list)) or not headers:
        raise XlsxInspectionError("XLSX_HEADERS_INVALID")
    normalized: list[str] = []
    for value in headers:
        if not isinstance(value, str):
            raise XlsxInspectionError("XLSX_HEADERS_INVALID")
        item = _normalized_header(value)
        if not item:
            raise XlsxInspectionError("XLSX_HEADERS_INVALID")
        normalized.append(item)
    return _canonical_hash(normalized)


@dataclass(frozen=True, slots=True)
class XlsxInspectionLimits:
    max_file_bytes: int
    max_archive_entries: int
    max_total_uncompressed_bytes: int
    max_entry_uncompressed_bytes: int
    max_compression_ratio: int
    max_xml_bytes: int
    max_rows: int
    max_columns: int

    def __post_init__(self) -> None:
        for field_name, value in asdict(self).items():
            _positive_int(value, f"XLSX_LIMIT_INVALID:{field_name}")
        if self.max_entry_uncompressed_bytes > self.max_total_uncompressed_bytes:
            raise XlsxInspectionError("XLSX_LIMIT_RELATION_INVALID")


@dataclass(frozen=True, slots=True)
class XlsxSchemaExpectation:
    schema_id: str
    schema_version: str
    schema_authority_reference: str
    direct_identifiers_expected: bool
    package_kind: str
    sheet_name: str
    sheet_count: int
    header_row_index: int
    header_sha256: str
    column_count: int
    min_data_rows: int
    max_data_rows: int
    max_formula_count: int

    def __post_init__(self) -> None:
        _safe_text(self.schema_id, "XLSX_SCHEMA_ID_INVALID")
        _safe_text(self.schema_version, "XLSX_SCHEMA_VERSION_INVALID")
        _safe_text(
            self.schema_authority_reference,
            "XLSX_SCHEMA_AUTHORITY_REFERENCE_INVALID",
        )
        if not isinstance(self.direct_identifiers_expected, bool):
            raise XlsxInspectionError("XLSX_SCHEMA_PII_FLAG_INVALID")
        if self.direct_identifiers_expected:
            raise XlsxInspectionError("XLSX_PERSONAL_DATA_SCHEMA_NOT_APPROVED")
        if self.package_kind not in {"XLSX", "ZIP_XLSX"}:
            raise XlsxInspectionError("XLSX_PACKAGE_KIND_INVALID")
        _safe_text(self.sheet_name, "XLSX_SHEET_NAME_INVALID")
        _positive_int(self.sheet_count, "XLSX_SHEET_COUNT_INVALID")
        _positive_int(self.header_row_index, "XLSX_HEADER_ROW_INVALID")
        if not isinstance(self.header_sha256, str) or _HEX_SHA256.fullmatch(self.header_sha256) is None:
            raise XlsxInspectionError("XLSX_HEADER_HASH_INVALID")
        _positive_int(self.column_count, "XLSX_COLUMN_COUNT_INVALID")
        if (
            not isinstance(self.min_data_rows, int)
            or isinstance(self.min_data_rows, bool)
            or self.min_data_rows < 0
            or not isinstance(self.max_data_rows, int)
            or isinstance(self.max_data_rows, bool)
            or self.max_data_rows < self.min_data_rows
        ):
            raise XlsxInspectionError("XLSX_ROW_RANGE_INVALID")
        if (
            not isinstance(self.max_formula_count, int)
            or isinstance(self.max_formula_count, bool)
            or self.max_formula_count < 0
        ):
            raise XlsxInspectionError("XLSX_FORMULA_LIMIT_INVALID")


@dataclass(frozen=True, slots=True)
class XlsxInspectionPolicy:
    policy_id: str
    version: int
    limits: XlsxInspectionLimits
    schemas: tuple[XlsxSchemaExpectation, ...]
    prohibited_header_tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        _safe_text(self.policy_id, "XLSX_POLICY_ID_INVALID")
        _positive_int(self.version, "XLSX_POLICY_VERSION_INVALID")
        if not isinstance(self.limits, XlsxInspectionLimits):
            raise XlsxInspectionError("XLSX_LIMITS_REQUIRED")
        if not isinstance(self.schemas, tuple) or not self.schemas:
            raise XlsxInspectionError("XLSX_SCHEMAS_REQUIRED")
        if any(not isinstance(item, XlsxSchemaExpectation) for item in self.schemas):
            raise XlsxInspectionError("XLSX_SCHEMA_INVALID")
        for schema in self.schemas:
            if schema.column_count > self.limits.max_columns:
                raise XlsxInspectionError("XLSX_SCHEMA_EXCEEDS_COLUMN_LIMIT")
            if schema.header_row_index > self.limits.max_rows:
                raise XlsxInspectionError("XLSX_SCHEMA_EXCEEDS_ROW_LIMIT")
            if schema.max_data_rows > self.limits.max_rows:
                raise XlsxInspectionError("XLSX_SCHEMA_EXCEEDS_ROW_LIMIT")
        header_rows: dict[tuple[str, str], int] = {}
        for schema in self.schemas:
            key = (schema.package_kind, schema.sheet_name)
            prior = header_rows.setdefault(key, schema.header_row_index)
            if prior != schema.header_row_index:
                raise XlsxInspectionError("XLSX_SCHEMA_HEADER_ROW_AMBIGUOUS")
        schema_keys = {(item.schema_id, item.schema_version) for item in self.schemas}
        if len(schema_keys) != len(self.schemas):
            raise XlsxInspectionError("XLSX_SCHEMA_DUPLICATE")
        if not isinstance(self.prohibited_header_tokens, tuple):
            raise XlsxInspectionError("XLSX_PROHIBITED_TOKENS_INVALID")
        normalized_tokens: list[str] = []
        for token in self.prohibited_header_tokens:
            normalized = _normalized_header(_safe_text(token, "XLSX_PROHIBITED_TOKEN_INVALID")).casefold()
            normalized_tokens.append(normalized)
        if len(set(normalized_tokens)) != len(normalized_tokens):
            raise XlsxInspectionError("XLSX_PROHIBITED_TOKEN_DUPLICATE")

    @property
    def content_hash(self) -> str:
        return _canonical_hash(
            {
                "policy_id": self.policy_id,
                "version": self.version,
                "limits": asdict(self.limits),
                "schemas": [asdict(item) for item in self.schemas],
                "prohibited_header_tokens": list(self.prohibited_header_tokens),
            }
        )


@dataclass(frozen=True, slots=True)
class XlsxPackageInspection:
    package_kind: str
    original_sha256: str
    original_size_bytes: int
    workbook_sha256: str
    workbook_size_bytes: int
    sheet_name: str
    sheet_count: int
    header_row_index: int
    header_sha256: str
    column_count: int
    data_row_count: int
    formula_count: int
    prohibited_header_count: int
    structural_fingerprint_sha256: str
    matched_schema_id: str | None
    matched_schema_version: str | None
    matched_schema_authority_reference: str | None
    diagnostics: tuple[str, ...]

    @property
    def matched(self) -> bool:
        return self.matched_schema_id is not None and not self.diagnostics
