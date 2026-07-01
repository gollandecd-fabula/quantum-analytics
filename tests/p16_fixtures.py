from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from io import BytesIO
import json
import unittest
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.access import TenantContext
from quantum.ingestion.admission import (
    AdmissionError,
    DatasetAdmissionState,
    DatasetControlEvidence,
    DatasetDeclaration,
    DatasetSensitivity,
    RealDatasetAdmissionRegistry,
    StorageControlEvidence,
)
from quantum.ingestion.xlsx_inspection import (
    XlsxInspectionError,
    XlsxInspectionLimits,
    XlsxInspectionPolicy,
    XlsxPackageInspector,
    XlsxSchemaExpectation,
    normalized_header_sha256,
)


HEADERS = ("operation_id", "operation_type", "amount")
NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def _content_types(*, macro: bool = False) -> bytes:
    workbook_type = (
        "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
        if macro
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="{workbook_type}"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>'''.encode()


def _root_rels(*, external: bool = False) -> bytes:
    extra = (
        '<Relationship Id="rExt" Type="urn:test" Target="https://example.invalid" TargetMode="External"/>'
        if external
        else ""
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
{extra}
</Relationships>'''.encode()


def _workbook(*, extra_sheet: bool = False) -> bytes:
    second = '<sheet name="HiddenData" sheetId="2" r:id="rId2"/>' if extra_sheet else ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/>{second}</sheets>
</workbook>'''.encode()


def _workbook_rels(*, extra_sheet: bool = False) -> bytes:
    second = (
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        if extra_sheet
        else ""
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
{second}
</Relationships>'''.encode()


def _inline_cell(reference: str, value: str, *, formula: str | None = None) -> str:
    formula_xml = f"<f>{formula}</f>" if formula is not None else ""
    escaped = (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return f'<c r="{reference}" t="inlineStr">{formula_xml}<is><t>{escaped}</t></is></c>'


def _column_name(index: int) -> str:
    value = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        value = chr(65 + remainder) + value
    return value


def build_xlsx(
    *,
    headers: tuple[str, ...] = HEADERS,
    rows: tuple[tuple[str, ...], ...] = (("1", "SALE", "100.00"),),
    formula: bool = False,
    macro: bool = False,
    external: bool = False,
    doctype: bool = False,
    extra_entries: dict[str, bytes] | None = None,
    extra_sheet: bool = False,
) -> bytes:
    sheet_rows: list[str] = []
    header_cells = "".join(
        _inline_cell(f"{_column_name(index)}1", value)
        for index, value in enumerate(headers, start=1)
    )
    sheet_rows.append(f'<row r="1">{header_cells}</row>')
    for row_index, values in enumerate(rows, start=2):
        cells = []
        for column_index, value in enumerate(values, start=1):
            cells.append(
                _inline_cell(
                    f"{_column_name(column_index)}{row_index}",
                    value,
                    formula="1+1" if formula and row_index == 2 and column_index == 3 else None,
                )
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    prefix = "<!DOCTYPE worksheet [<!ENTITY x 'bad'>]>" if doctype else ""
    sheet = f'''<?xml version="1.0" encoding="UTF-8"?>{prefix}
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData>{"".join(sheet_rows)}</sheetData>
</worksheet>'''.encode()

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types(macro=macro))
        zf.writestr("_rels/.rels", _root_rels(external=external))
        zf.writestr("xl/workbook.xml", _workbook(extra_sheet=extra_sheet))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(extra_sheet=extra_sheet))
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
        if extra_sheet:
            zf.writestr("xl/worksheets/sheet2.xml", sheet)
        if macro:
            zf.writestr("xl/vbaProject.bin", b"macro")
        for name, payload in (extra_entries or {}).items():
            zf.writestr(name, payload)
    return buffer.getvalue()


def rewrite_xlsx_part(workbook: bytes, part_name: str, transform) -> bytes:
    source = BytesIO(workbook)
    output = BytesIO()
    with ZipFile(source) as current, ZipFile(
        output, "w", compression=ZIP_DEFLATED
    ) as rewritten:
        for info in current.infolist():
            payload = current.read(info)
            if info.filename == part_name:
                payload = transform(payload)
            rewritten.writestr(info.filename, payload)
    return output.getvalue()


def wrap_xlsx(workbook: bytes, *, name: str = "weekly-report.xlsx") -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr(name, workbook)
    return buffer.getvalue()


def policy(*, headers: tuple[str, ...] = HEADERS, formulas: int = 0):
    limits = XlsxInspectionLimits(
        max_file_bytes=2_000_000,
        max_archive_entries=64,
        max_total_uncompressed_bytes=4_000_000,
        max_entry_uncompressed_bytes=2_000_000,
        max_compression_ratio=200,
        max_xml_bytes=1_000_000,
        max_rows=1000,
        max_columns=100,
    )
    direct = XlsxSchemaExpectation(
        schema_id="wb-weekly-synthetic-v1",
        schema_version="1.0",
        schema_authority_reference="schema-review-001",
        direct_identifiers_expected=False,
        package_kind="XLSX",
        sheet_name="Sheet1",
        sheet_count=1,
        header_row_index=1,
        header_sha256=normalized_header_sha256(headers),
        column_count=len(headers),
        min_data_rows=1,
        max_data_rows=100,
        max_formula_count=formulas,
    )
    wrapped = XlsxSchemaExpectation(
        schema_id="wb-weekly-synthetic-zip-v1",
        schema_version="1.0",
        schema_authority_reference="schema-review-001",
        direct_identifiers_expected=False,
        package_kind="ZIP_XLSX",
        sheet_name="Sheet1",
        sheet_count=1,
        header_row_index=1,
        header_sha256=normalized_header_sha256(headers),
        column_count=len(headers),
        min_data_rows=1,
        max_data_rows=100,
        max_formula_count=formulas,
    )
    return XlsxInspectionPolicy(
        policy_id="real-xlsx-synthetic-policy",
        version=1,
        limits=limits,
        schemas=(direct, wrapped),
        prohibited_header_tokens=(
            "phone", "email", "address", "customer name", "телефон", "адрес", "фио"
        ),
    )


def declaration(tenant: TenantContext, payload: bytes, *, rows: int = 1):
    return DatasetDeclaration(
        dataset_id=str(uuid4()),
        tenant_id=tenant.tenant_id,
        uploader_account_id=tenant.account_id,
        source_internal_id="src-wb-week-001",
        marketplace="wildberries",
        report_type="weekly-detailed",
        reporting_period_start=date(2026, 6, 1),
        reporting_period_end=date(2026, 6, 7),
        timezone="Europe/Moscow",
        original_file_sha256=sha256(payload).hexdigest(),
        original_size_bytes=len(payload),
        expected_row_count=rows,
        control_totals_sha256="0" * 64,
        data_categories=("financial_operations", "product_identifiers"),
        sensitivity=DatasetSensitivity.COMMERCIAL_CONFIDENTIAL,
        owner_authority_reference="owner-attestation-001",
        lawful_authority_attested=True,
        retention_deadline=NOW + timedelta(days=30),
        declared_at=NOW,
    )


def evidence(tenant: TenantContext, dataset, **overrides):
    values = {
        "evidence_id": "storage-evidence-001",
        "tenant_id": tenant.tenant_id,
        "dataset_id": dataset.declaration.dataset_id,
        "original_file_sha256": dataset.declaration.original_file_sha256,
        "storage_key_sha256": sha256(b"tenant-scoped-storage-key").hexdigest(),
        "transport_encrypted": True,
        "encryption_at_rest": True,
        "tenant_scoped_paths": True,
        "immutable_original": True,
        "separated_quarantine_and_admitted_zones": True,
        "least_privilege_credentials": True,
        "verified_at": NOW + timedelta(minutes=1),
        "verifier_account_id": tenant.account_id,
    }
    values.update(overrides)
    return StorageControlEvidence(**values)


def dataset_evidence(tenant: TenantContext, dataset, **overrides):
    values = {
        "evidence_id": "dataset-evidence-001",
        "tenant_id": tenant.tenant_id,
        "dataset_id": dataset.declaration.dataset_id,
        "original_file_sha256": dataset.declaration.original_file_sha256,
        "source_authority_verified": True,
        "report_period_verified": True,
        "control_totals_verified": True,
        "direct_identifiers_absent_or_approved": True,
        "malware_scan_clean": True,
        "malware_scan_evidence_sha256": sha256(b"synthetic-malware-scan").hexdigest(),
        "verified_at": NOW + timedelta(minutes=1),
        "verifier_account_id": tenant.account_id,
    }
    values.update(overrides)
    return DatasetControlEvidence(**values)
