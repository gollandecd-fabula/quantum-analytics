from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import traceback
from typing import Any, Mapping
from zipfile import BadZipFile, ZipFile

from quantum.ingestion._xlsx_archive import (
    _cell_position,
    _cell_text,
    _extract_workbook,
    _read_limited,
    _shared_strings,
    _xml_root,
)
from quantum.ingestion._xlsx_contracts import (
    XlsxInspectionError,
    XlsxInspectionLimits,
    normalized_header_sha256,
)
from quantum.ingestion import _xlsx_relationships_core as _relationship_core

from . import local_runner as _engine


_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_RELATIONSHIP_NS = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_RELATIONSHIP = f"{{{_RELATIONSHIP_NS}}}Relationship"
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_HEADER_KEYWORDS = (
    "артикул",
    "номенклатур",
    "дата",
    "сумм",
    "комисс",
    "логист",
    "продаж",
    "колич",
    "бренд",
    "предмет",
    "заказ",
    "возврат",
    "удержан",
    "article",
    "date",
    "amount",
    "commission",
    "logistic",
    "sale",
    "quantity",
    "brand",
    "order",
    "return",
)


class WindowsRunnerError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DiscoveredSchema:
    package_kind: str
    sheet_name: str
    sheet_count: int
    header_row_index: int
    headers: tuple[str, ...]
    header_sha256: str
    column_count: int
    data_row_count: int
    formula_count: int

    def report(self) -> dict[str, Any]:
        return {
            "package_kind": self.package_kind,
            "sheet_name": self.sheet_name,
            "sheet_count": self.sheet_count,
            "header_row_index": self.header_row_index,
            "headers": list(self.headers),
            "header_sha256": self.header_sha256,
            "column_count": self.column_count,
            "data_row_count": self.data_row_count,
            "formula_count": self.formula_count,
        }


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    _atomic_bytes(path.resolve(), encoded)


def _workbook_target_compatible(target: str) -> str:
    if not isinstance(target, str):
        raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
    normalized = target.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("//")
        or _URI_SCHEME.match(normalized)
        or ":" in normalized
    ):
        raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
    package_absolute = normalized.startswith("/")
    if package_absolute:
        normalized = normalized[1:]
    pieces = normalized.split("/")
    if any(not piece or piece in {".", ".."} for piece in pieces):
        raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
    joined = "/".join(pieces).casefold()
    if package_absolute:
        if not joined.startswith("xl/"):
            raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
        return joined
    return "xl/" + joined


def install_windows_compatibility() -> None:
    _engine._atomic_bytes = _atomic_bytes
    _relationship_core._workbook_target = _workbook_target_compatible


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WindowsRunnerError(code)
    return value


def _positive_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise WindowsRunnerError(code)
    return value


def _limits(config: Mapping[str, Any]) -> XlsxInspectionLimits:
    policy = _mapping(config.get("inspection_policy"), "LOCAL_PILOT_POLICY_INVALID")
    raw = _mapping(policy.get("limits"), "LOCAL_PILOT_LIMITS_INVALID")
    try:
        return XlsxInspectionLimits(**dict(raw))
    except (TypeError, XlsxInspectionError) as exc:
        raise WindowsRunnerError("LOCAL_PILOT_LIMITS_INVALID") from exc


def _row_values(row, shared: tuple[str, ...], max_columns: int) -> tuple[tuple[str, ...], int]:
    values: dict[int, str] = {}
    formula_count = 0
    for cell in row.findall(f"{{{_SPREADSHEET_NS}}}c"):
        reference = cell.get("r") or ""
        column, _ = _cell_position(reference)
        if column > max_columns:
            raise XlsxInspectionError("XLSX_COLUMN_LIMIT_EXCEEDED")
        if column in values:
            raise XlsxInspectionError("XLSX_CELL_DUPLICATE")
        values[column] = _cell_text(cell, shared).strip()
        if cell.find(f"{{{_SPREADSHEET_NS}}}f") is not None:
            formula_count += 1
    if not values:
        return (), formula_count
    last = max(values)
    return tuple(values.get(index, "") for index in range(1, last + 1)), formula_count


def _candidate_score(headers: tuple[str, ...], row_index: int) -> int:
    text_cells = sum(any(character.isalpha() for character in value) for value in headers)
    normalized = tuple(" ".join(value.split()).casefold() for value in headers)
    keyword_hits = sum(
        any(keyword in value for keyword in _HEADER_KEYWORDS) for value in normalized
    )
    unique = len(set(normalized))
    return (
        len(headers) * 100
        + text_cells * 20
        + keyword_hits * 50
        + unique * 5
        - min(row_index, 1000)
    )


def discover_schema(
    *,
    payload: bytes,
    limits: XlsxInspectionLimits,
    max_scan_rows: int = 100,
    min_columns: int = 3,
) -> DiscoveredSchema:
    if not isinstance(payload, bytes) or not payload:
        raise WindowsRunnerError("XLSX_BYTES_REQUIRED")
    max_scan_rows = min(
        _positive_int(max_scan_rows, "XLSX_DISCOVERY_ROW_LIMIT_INVALID"),
        limits.max_rows,
    )
    min_columns = min(
        _positive_int(min_columns, "XLSX_DISCOVERY_COLUMN_LIMIT_INVALID"),
        limits.max_columns,
    )
    package_kind, workbook = _extract_workbook(payload, limits)
    candidates: list[tuple[int, DiscoveredSchema]] = []
    try:
        from io import BytesIO

        with ZipFile(BytesIO(workbook)) as archive:
            workbook_root = _xml_root(
                _read_limited(archive, "xl/workbook.xml", limits),
                "XLSX_WORKBOOK_INVALID",
            )
            relationship_root = _xml_root(
                _read_limited(
                    archive,
                    "xl/_rels/workbook.xml.rels",
                    limits,
                ),
                "XLSX_WORKBOOK_RELATIONSHIPS_INVALID",
            )
            relationship_map: dict[str, str] = {}
            for relation in relationship_root.findall(_RELATIONSHIP):
                relationship_id = relation.get("Id")
                if not relationship_id or relationship_id in relationship_map:
                    raise XlsxInspectionError("XLSX_WORKBOOK_RELATIONSHIPS_INVALID")
                relationship_map[relationship_id] = _workbook_target_compatible(
                    relation.get("Target") or ""
                )
            sheets = workbook_root.find(f"{{{_SPREADSHEET_NS}}}sheets")
            if sheets is None:
                raise XlsxInspectionError("XLSX_SHEETS_MISSING")
            sheet_nodes = sheets.findall(f"{{{_SPREADSHEET_NS}}}sheet")
            if not sheet_nodes:
                raise XlsxInspectionError("XLSX_SHEETS_MISSING")
            shared = _shared_strings(archive, limits)
            sheet_count = len(sheet_nodes)
            for sheet in sheet_nodes:
                sheet_name = (sheet.get("name") or "").strip()
                relationship_id = sheet.get(f"{{{_OFFICE_RELATIONSHIP_NS}}}id")
                sheet_path = relationship_map.get(relationship_id or "")
                if not sheet_name or sheet_path is None:
                    raise XlsxInspectionError("XLSX_SHEET_RELATIONSHIP_MISSING")
                if not (
                    sheet_path.startswith("xl/worksheets/")
                    and sheet_path.endswith(".xml")
                ):
                    continue
                sheet_root = _xml_root(
                    _read_limited(archive, sheet_path, limits),
                    "XLSX_WORKSHEET_INVALID",
                )
                sheet_data = sheet_root.find(f"{{{_SPREADSHEET_NS}}}sheetData")
                if sheet_data is None:
                    continue
                rows = sheet_data.findall(f"{{{_SPREADSHEET_NS}}}row")
                parsed_rows: list[tuple[int, tuple[str, ...], int]] = []
                total_formulas = 0
                for row in rows:
                    raw_index = row.get("r") or "0"
                    try:
                        row_index = int(raw_index)
                    except ValueError as exc:
                        raise XlsxInspectionError("XLSX_ROW_INDEX_INVALID") from exc
                    values, formulas = _row_values(row, shared, limits.max_columns)
                    total_formulas += formulas
                    parsed_rows.append((row_index, values, formulas))
                for row_index, values, _ in parsed_rows:
                    if row_index > max_scan_rows:
                        continue
                    if len(values) < min_columns or any(not value for value in values):
                        continue
                    data_row_count = sum(
                        bool(candidate_values)
                        and any(value for value in candidate_values)
                        and candidate_index > row_index
                        for candidate_index, candidate_values, _ in parsed_rows
                    )
                    candidate = DiscoveredSchema(
                        package_kind=package_kind,
                        sheet_name=sheet_name,
                        sheet_count=sheet_count,
                        header_row_index=row_index,
                        headers=values,
                        header_sha256=normalized_header_sha256(values),
                        column_count=len(values),
                        data_row_count=data_row_count,
                        formula_count=total_formulas,
                    )
                    candidates.append((_candidate_score(values, row_index), candidate))
    except XlsxInspectionError:
        raise
    except (BadZipFile, OSError, EOFError, ValueError) as exc:
        raise XlsxInspectionError("XLSX_ARCHIVE_INVALID") from exc
    if not candidates:
        raise WindowsRunnerError("XLSX_SCHEMA_DISCOVERY_FAILED")
    candidates.sort(
        key=lambda item: (
            item[0],
            item[1].column_count,
            -item[1].header_row_index,
            item[1].sheet_name,
        ),
        reverse=True,
    )
    best_score, best = candidates[0]
    if len(candidates) > 1 and candidates[1][0] == best_score:
        other = candidates[1][1]
        if (
            other.sheet_name != best.sheet_name
            or other.header_row_index != best.header_row_index
            or other.header_sha256 != best.header_sha256
        ):
            raise WindowsRunnerError("XLSX_SCHEMA_DISCOVERY_AMBIGUOUS")
    return best


def apply_discovered_schema(
    config: Mapping[str, Any], candidate: DiscoveredSchema
) -> dict[str, Any]:
    updated = json.loads(json.dumps(dict(config), ensure_ascii=False))
    policy = _mapping(updated.get("inspection_policy"), "LOCAL_PILOT_POLICY_INVALID")
    schemas = policy.get("schemas")
    if not isinstance(schemas, list) or not schemas:
        raise WindowsRunnerError("LOCAL_PILOT_SCHEMAS_REQUIRED")
    template = dict(_mapping(schemas[0], "LOCAL_PILOT_SCHEMA_INVALID"))
    template.update(
        {
            "schema_id": str(template.get("schema_id", "WB_REPORT"))
            + "-HOME-DISCOVERED",
            "schema_version": str(template.get("schema_version", "1"))
            + "-home",
            "schema_authority_reference": "HOME_LOCAL_OPERATOR_REVIEW",
            "direct_identifiers_expected": False,
            "package_kind": candidate.package_kind,
            "sheet_name": candidate.sheet_name,
            "sheet_count": candidate.sheet_count,
            "header_row_index": candidate.header_row_index,
            "header_sha256": candidate.header_sha256,
            "column_count": candidate.column_count,
            "min_data_rows": 0,
            "max_data_rows": max(
                int(template.get("max_data_rows", 0)),
                candidate.data_row_count,
            ),
            "max_formula_count": max(
                int(template.get("max_formula_count", 0)),
                candidate.formula_count,
            ),
        }
    )
    policy["schemas"] = [template]
    updated["inspection_policy"] = dict(policy)
    updated["expected_row_count"] = candidate.data_row_count
    updated["schema_discovery"] = candidate.report()
    return updated


def _safe_error(exc: Exception, *, debug: bool) -> dict[str, Any]:
    code = getattr(exc, "code", "LOCAL_PILOT_UNEXPECTED_ERROR")
    payload: dict[str, Any] = {
        "status": "ERROR",
        "code": code,
        "detail": type(exc).__name__,
    }
    if isinstance(exc, OSError) and exc.errno is not None:
        payload["errno"] = exc.errno
    if debug:
        payload["message"] = str(exc)
        payload["traceback"] = traceback.format_exc()
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Windows-compatible loopback-only Quantum local pilot"
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--home-local", action="store_true")
    parser.add_argument("--discover-schema", action="store_true")
    parser.add_argument("--authority-attested", action="store_true")
    parser.add_argument("--schema-reviewed", action="store_true")
    parser.add_argument("--max-scan-rows", type=int, default=100)
    parser.add_argument("--min-header-columns", type=int, default=3)
    parser.add_argument("--debug-errors", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    install_windows_compatibility()
    try:
        raw_config = json.loads(args.config.read_text(encoding="utf-8"))
        config = dict(_mapping(raw_config, "LOCAL_PILOT_CONFIG_INVALID"))
        if args.home_local:
            if not args.authority_attested:
                raise WindowsRunnerError("HOME_LOCAL_AUTHORITY_ATTESTATION_REQUIRED")
            config["lawful_authority_attested"] = True
        if args.discover_schema:
            if not args.home_local:
                raise WindowsRunnerError("SCHEMA_DISCOVERY_HOME_LOCAL_ONLY")
            if not args.schema_reviewed:
                raise WindowsRunnerError("SCHEMA_DISCOVERY_REVIEW_REQUIRED")
            candidate = discover_schema(
                payload=args.file.read_bytes(),
                limits=_limits(config),
                max_scan_rows=args.max_scan_rows,
                min_columns=args.min_header_columns,
            )
            config = apply_discovered_schema(config, candidate)
        else:
            candidate = None
        report = _engine.run_local_pilot(
            file_path=args.file,
            config=config,
            storage_root=args.storage_root,
        )
        report["runtime_profile"] = "HOME_LOCAL" if args.home_local else "CONTROLLED_LOCAL"
        report["storage_encryption_required"] = not args.home_local
        if candidate is not None:
            report["schema_discovery"] = candidate.report()
        if args.home_local:
            limitations = list(report.get("limitations", []))
            for item in (
                "HOME_LOCAL_UNENCRYPTED_STORAGE",
                "PHYSICAL_ACCESS_RISK_ACCEPTED",
            ):
                if item not in limitations:
                    limitations.append(item)
            report["limitations"] = limitations
        _atomic_json(args.output, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "output": str(args.output),
                    "runtime_profile": report["runtime_profile"],
                },
                ensure_ascii=False,
            )
        )
        if report["status"] not in {
            "PILOT_RUN_COMPLETE",
            "CALCULATED_RECONCILIATION_PENDING",
        }:
            return 2
        return 0
    except Exception as exc:
        print(
            json.dumps(
                _safe_error(exc, debug=args.debug_errors),
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
