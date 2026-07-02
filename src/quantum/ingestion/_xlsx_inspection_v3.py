from __future__ import annotations

from hashlib import sha256

from ._xlsx_archive import _extract_workbook
from ._xlsx_cell_structure import validate_cell_structures
from ._xlsx_content_model import validate_modeled_xml_content
from ._xlsx_contracts import (
    XlsxInspectionError,
    XlsxInspectionLimits,
    XlsxInspectionPolicy,
    XlsxPackageInspection,
    XlsxSchemaExpectation,
    _canonical_hash,
    normalized_header_sha256,
)
from ._xlsx_package_parts import validate_modeled_package_parts
from ._xlsx_r19_hardening import (
    validate_archive_extra_fields,
    validate_workbook_r19_hardening,
)
from ._xlsx_relationships import validate_relationships
from ._xlsx_workbook import _workbook_shape
from ._xlsx_workbook_content import validate_workbook_xml_content
from ._xlsx_worksheet_attributes import validate_worksheet_structural_attributes
from ._xlsx_xml_lexical import validate_xml_lexical_content
from ._xlsx_zip_coverage import validate_zip_record_coverage


class XlsxPackageInspector:
    def inspect(
        self,
        *,
        payload: bytes,
        policy: XlsxInspectionPolicy,
    ) -> XlsxPackageInspection:
        if not isinstance(payload, bytes) or not payload:
            raise XlsxInspectionError("XLSX_BYTES_REQUIRED")
        if not isinstance(policy, XlsxInspectionPolicy):
            raise XlsxInspectionError("XLSX_POLICY_REQUIRED")
        validate_zip_record_coverage(payload)
        validate_archive_extra_fields(payload)
        package_kind, workbook = _extract_workbook(payload, policy.limits)
        if len(workbook) > policy.limits.max_file_bytes:
            raise XlsxInspectionError("XLSX_WORKBOOK_SIZE_EXCEEDED")
        if package_kind == "ZIP_XLSX":
            validate_zip_record_coverage(workbook)
            validate_archive_extra_fields(workbook)
        validate_workbook_r19_hardening(workbook, policy.limits)
        content_types_part = validate_modeled_package_parts(
            workbook,
            policy.limits,
        )
        validate_xml_lexical_content(workbook, policy.limits)
        workbook_part = validate_workbook_xml_content(workbook, policy.limits)
        auxiliary_parts = validate_modeled_xml_content(workbook, policy.limits)
        worksheet_parts = validate_worksheet_structural_attributes(
            workbook,
            policy.limits,
        )
        relationship_parts = validate_relationships(workbook, policy.limits)
        validate_cell_structures(workbook, policy.limits)
        shape = _workbook_shape(
            workbook,
            policy=policy,
            package_kind=package_kind,
        )

        matches: list[XlsxSchemaExpectation] = []
        mismatch_codes: set[str] = set()
        candidates = [
            schema
            for schema in policy.schemas
            if schema.package_kind == package_kind
        ]
        if not candidates:
            mismatch_codes.add("XLSX_PACKAGE_KIND_UNREGISTERED")
        for schema in candidates:
            local: set[str] = set()
            if shape.sheet_name != schema.sheet_name:
                local.add("XLSX_SHEET_NAME_MISMATCH")
            if shape.sheet_count != schema.sheet_count:
                local.add("XLSX_SHEET_COUNT_MISMATCH")
            if shape.header_row_index != schema.header_row_index:
                local.add("XLSX_HEADER_ROW_MISMATCH")
            if shape.header_sha256 != schema.header_sha256:
                local.add("XLSX_HEADER_HASH_MISMATCH")
            if shape.column_count != schema.column_count:
                local.add("XLSX_COLUMN_COUNT_MISMATCH")
            if shape.max_used_column > schema.column_count:
                local.add("XLSX_DATA_COLUMN_COUNT_EXCEEDED")
            if shape.unmodeled_worksheet_count:
                local.add("XLSX_UNMODELED_WORKSHEET_CONTENT")
            if not (
                schema.min_data_rows
                <= shape.data_row_count
                <= schema.max_data_rows
            ):
                local.add("XLSX_ROW_COUNT_OUT_OF_RANGE")
            if shape.formula_count > schema.max_formula_count:
                local.add("XLSX_FORMULA_COUNT_EXCEEDED")
            if local:
                mismatch_codes.update(local)
            else:
                matches.append(schema)

        matched: XlsxSchemaExpectation | None = None
        if len(matches) == 1:
            matched = matches[0]
        elif len(matches) > 1:
            mismatch_codes.add("XLSX_SCHEMA_MATCH_AMBIGUOUS")
        if shape.prohibited_header_count:
            mismatch_codes.add("XLSX_DIRECT_IDENTIFIER_HEADER_PRESENT")
            matched = None
        if matched is None and not matches:
            mismatch_codes.add("XLSX_SCHEMA_UNKNOWN")

        structural = {
            "package_kind": package_kind,
            "sheet_name": shape.sheet_name,
            "sheet_count": shape.sheet_count,
            "header_row_index": shape.header_row_index,
            "header_sha256": shape.header_sha256,
            "column_count": shape.column_count,
            "max_used_column": shape.max_used_column,
            "unmodeled_worksheet_count": shape.unmodeled_worksheet_count,
            "data_row_count": shape.data_row_count,
            "formula_count": shape.formula_count,
            "prohibited_header_count": shape.prohibited_header_count,
            "content_types_part": content_types_part,
            "workbook_part": workbook_part,
            "worksheet_parts": worksheet_parts,
            "relationship_parts": relationship_parts,
            "auxiliary_parts": auxiliary_parts,
        }
        diagnostics = tuple(sorted(mismatch_codes)) if matched is None else ()
        return XlsxPackageInspection(
            package_kind=package_kind,
            original_sha256=sha256(payload).hexdigest(),
            original_size_bytes=len(payload),
            workbook_sha256=sha256(workbook).hexdigest(),
            workbook_size_bytes=len(workbook),
            sheet_name=shape.sheet_name,
            sheet_count=shape.sheet_count,
            header_row_index=shape.header_row_index,
            header_sha256=shape.header_sha256,
            column_count=shape.column_count,
            data_row_count=shape.data_row_count,
            formula_count=shape.formula_count,
            prohibited_header_count=shape.prohibited_header_count,
            structural_fingerprint_sha256=_canonical_hash(structural),
            matched_schema_id=matched.schema_id if matched else None,
            matched_schema_version=matched.schema_version if matched else None,
            matched_schema_authority_reference=(
                matched.schema_authority_reference if matched else None
            ),
            diagnostics=diagnostics,
        )


__all__ = [
    "XlsxInspectionError",
    "XlsxInspectionLimits",
    "XlsxInspectionPolicy",
    "XlsxPackageInspection",
    "XlsxPackageInspector",
    "XlsxSchemaExpectation",
    "normalized_header_sha256",
]
