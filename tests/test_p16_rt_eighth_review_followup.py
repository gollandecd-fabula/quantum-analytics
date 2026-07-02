import unittest
from io import BytesIO
from zipfile import ZipFile

from tests.p16_fixtures import *  # noqa: F403


_END_RECORD = b"PK\x05\x06"
_CENTRAL_HEADER = b"PK\x01\x02"


def _insert_gap_before_central_directory(payload: bytes) -> bytes:
    gap = b"unmodeled-gap-before-central-directory"
    end_offset = payload.rfind(_END_RECORD)
    central_offset = int.from_bytes(payload[end_offset + 16 : end_offset + 20], "little")
    mutated = bytearray(payload[:central_offset] + gap + payload[central_offset:])
    new_end_offset = end_offset + len(gap)
    mutated[new_end_offset + 16 : new_end_offset + 20] = (
        central_offset + len(gap)
    ).to_bytes(4, "little")
    return bytes(mutated)


def _insert_gap_between_local_records(payload: bytes) -> bytes:
    gap = b"unmodeled-gap-between-local-records"
    with ZipFile(BytesIO(payload)) as zf:
        offsets = sorted(info.header_offset for info in zf.infolist())
    insertion_offset = offsets[1]
    end_offset = payload.rfind(_END_RECORD)
    central_offset = int.from_bytes(payload[end_offset + 16 : end_offset + 20], "little")
    mutated = bytearray(payload[:insertion_offset] + gap + payload[insertion_offset:])
    new_central_offset = central_offset + len(gap)
    new_end_offset = end_offset + len(gap)
    cursor = new_central_offset
    while cursor < new_end_offset:
        if mutated[cursor : cursor + 4] != _CENTRAL_HEADER:
            raise AssertionError("central directory fixture malformed")
        name_size = int.from_bytes(mutated[cursor + 28 : cursor + 30], "little")
        extra_size = int.from_bytes(mutated[cursor + 30 : cursor + 32], "little")
        comment_size = int.from_bytes(mutated[cursor + 32 : cursor + 34], "little")
        local_offset = int.from_bytes(mutated[cursor + 42 : cursor + 46], "little")
        if local_offset >= insertion_offset:
            mutated[cursor + 42 : cursor + 46] = (
                local_offset + len(gap)
            ).to_bytes(4, "little")
        cursor += 46 + name_size + extra_size + comment_size
    mutated[new_end_offset + 16 : new_end_offset + 20] = new_central_offset.to_bytes(
        4,
        "little",
    )
    return bytes(mutated)


def _shared_payload(values: tuple[str, ...], *, hidden: bool = False) -> bytes:
    entries = []
    for index, value in enumerate(values):
        extra = "<ext><secret>hidden-text</secret></ext>" if hidden and index == 0 else ""
        entries.append(f"<si><t>{value}</t>{extra}</si>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + "".join(entries)
        + "</sst>"
    ).encode("utf-8")


def _use_shared_indexes(payload: bytes, values: tuple[str, ...]) -> bytes:
    replacements = tuple(
        zip(
            ("A1", "B1", "C1", "A2", "B2", "C2"),
            values,
            range(len(values)),
        )
    )
    text = payload.decode("utf-8")
    for reference, value, index in replacements:
        text = text.replace(
            f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>',
            f'<c r="{reference}" t="s"><v>{index}</v></c>',
        )
    return text.encode("utf-8")


class P16EighthReviewFollowupTests(unittest.TestCase):
    def test_gap_before_central_directory_is_rejected(self):
        payload = _insert_gap_before_central_directory(build_xlsx())
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")

    def test_gap_between_local_records_is_rejected(self):
        payload = _insert_gap_between_local_records(build_xlsx())
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")

    def test_wrapped_inner_gap_is_rejected(self):
        workbook = _insert_gap_before_central_directory(build_xlsx())
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=wrap_xlsx(workbook),
                policy=policy(),
            )
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")

    def test_root_text_before_sheet_data_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b"hidden-root-text<sheetData>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_UNMODELED_WORKSHEET_TEXT")

    def test_unknown_row_child_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"</row>",
                b"<ext><secret>hidden-text</secret></ext></row>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_SHEET_DATA_CONTENT_UNMODELED",
        )

    def test_inline_string_hidden_descendant_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<is><t>1</t></is>",
                b"<is><t>1</t><ext><secret>hidden-text</secret></ext></is>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_INLINE_STRING_STRUCTURE_UNMODELED",
        )

    def test_referenced_shared_string_hidden_descendant_is_rejected(self):
        values = (
            "operation_id",
            "operation_type",
            "amount",
            "1",
            "SALE",
            "100.00",
        )
        payload = rewrite_xlsx_part(
            build_xlsx(
                extra_entries={
                    "xl/sharedStrings.xml": _shared_payload(values, hidden=True),
                }
            ),
            "xl/worksheets/sheet1.xml",
            lambda value: _use_shared_indexes(value, values),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_SHARED_STRING_STRUCTURE_UNMODELED",
        )

    def test_auxiliary_xml_content_is_rejected(self):
        payload = build_xlsx(
            extra_entries={
                "docProps/core.xml": b'<core owner="alpha"><title>first</title></core>',
            }
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_AUXILIARY_CONTENT_UNMODELED")


if __name__ == "__main__":
    unittest.main()
