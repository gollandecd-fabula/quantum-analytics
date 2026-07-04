from __future__ import annotations

from dataclasses import replace
from io import BytesIO
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.ingestion._xlsx_auxiliary_content import validate_auxiliary_content
from quantum.ingestion._xlsx_contracts import (
    XlsxInspectionError,
    XlsxInspectionLimits,
    XlsxInspectionPolicy,
    XlsxSchemaExpectation,
    normalized_header_sha256,
)
from quantum.ingestion.xlsx_inspection import XlsxPackageInspector
from xml.etree import ElementTree


SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
XR = "http://schemas.microsoft.com/office/spreadsheetml/2014/revision"
X15 = "http://schemas.microsoft.com/office/spreadsheetml/2010/11/main"
AP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
AX = "http://schemas.microsoft.com/office/2006/activeX"
V = "urn:schemas-microsoft-com:vml"

HEADERS = ("Артикул", "Количество продаж", "Сумма продаж")


def _content_types() -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="{CONTENT_TYPES}">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>'''.encode("utf-8")


def _root_rels() -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{REL_PACKAGE}">
  <Relationship Id="rId1" Type="{REL_OFFICE}/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''.encode("utf-8")


def _workbook() -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="{SPREADSHEET}" xmlns:r="{REL_OFFICE}" xmlns:mc="{MC}" xmlns:x15="{X15}" mc:Ignorable="x15">
  <fileVersion appName="xl" lastEdited="7" lowestEdited="7" rupBuild="27126"/>
  <workbookPr filterPrivacy="1" defaultThemeVersion="164011"/>
  <bookViews><workbookView xWindow="0" yWindow="0" windowWidth="24000" windowHeight="12000" activeTab="0"/></bookViews>
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
  <calcPr calcId="122211"/>
</workbook>'''.encode("utf-8")


def _workbook_rels() -> bytes:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{REL_PACKAGE}">
  <Relationship Id="rId1" Type="{REL_OFFICE}/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>'''.encode("utf-8")


def _sheet(*, ignorable: str = "x15 xr v", uid: str = "{00000000-0001-0000-0000-000000000000}", used_unknown: bool = False) -> bytes:
    unknown_decl = ' xmlns:evil="urn:unexpected"' if used_unknown else ""
    unknown = '<evil:payload/>' if used_unknown else ""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="{SPREADSHEET}"
 xmlns:mc="{MC}"
 xmlns:xr="{XR}"
 xmlns:x15="{X15}"
 xmlns:ap="{AP}"
 xmlns:ax="{AX}"
 xmlns:v="{V}"{unknown_decl}
 mc:Ignorable="{ignorable}"
 xr:uid="{uid}">
  <dimension ref="A1:C2"/>
  <sheetViews><sheetView workbookViewId="0"/></sheetViews>
  <sheetFormatPr defaultRowHeight="15"/>
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>{HEADERS[0]}</t></is></c>
      <c r="B1" t="inlineStr"><is><t>{HEADERS[1]}</t></is></c>
      <c r="C1" t="inlineStr"><is><t>{HEADERS[2]}</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>SKU-1</t></is></c>
      <c r="B2"><v>1</v></c>
      <c r="C2"><v>100</v></c>
    </row>
  </sheetData>
  {unknown}
</worksheet>'''.encode("utf-8")


def build_realistic_xlsx(*, ignorable: str = "x15 xr v", uid: str = "{00000000-0001-0000-0000-000000000000}", used_unknown: bool = False) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types())
        zf.writestr("_rels/.rels", _root_rels())
        zf.writestr("xl/workbook.xml", _workbook())
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels())
        zf.writestr("xl/worksheets/sheet1.xml", _sheet(ignorable=ignorable, uid=uid, used_unknown=used_unknown))
    return buffer.getvalue()


def policy() -> XlsxInspectionPolicy:
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
    schema = XlsxSchemaExpectation(
        schema_id="realistic-office-v1",
        schema_version="1",
        schema_authority_reference="test",
        direct_identifiers_expected=False,
        package_kind="XLSX",
        sheet_name="Sheet1",
        sheet_count=1,
        header_row_index=1,
        header_sha256=normalized_header_sha256(HEADERS),
        column_count=3,
        min_data_rows=1,
        max_data_rows=10,
        max_formula_count=0,
    )
    return XlsxInspectionPolicy(
        policy_id="realistic-office-policy",
        version=1,
        limits=limits,
        schemas=(schema,),
        prohibited_header_tokens=("email", "phone"),
    )


class RealOfficeNamespaceCompatibilityTests(unittest.TestCase):
    def test_declaration_only_office_namespaces_are_accepted(self):
        inspection = XlsxPackageInspector().inspect(
            payload=build_realistic_xlsx(),
            policy=policy(),
        )
        self.assertEqual(inspection.diagnostics, ())
        self.assertEqual(inspection.data_row_count, 1)
        self.assertEqual(inspection.column_count, 3)

    def test_used_unknown_namespace_is_rejected(self):
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=build_realistic_xlsx(used_unknown=True),
                policy=policy(),
            )
        self.assertEqual(error.exception.code, "XLSX_XML_NAMESPACE_UNMODELED")

    def test_undeclared_ignorable_prefix_is_rejected(self):
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=build_realistic_xlsx(ignorable="x15 xr v ghost"),
                policy=policy(),
            )
        self.assertEqual(error.exception.code, "XLSX_XML_NAMESPACE_UNMODELED")

    def test_invalid_revision_uid_is_rejected(self):
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=build_realistic_xlsx(uid="not-a-guid"),
                policy=policy(),
            )
        self.assertEqual(error.exception.code, "XLSX_WORKSHEET_ATTRIBUTE_VALUE_INVALID")

    def test_standard_auxiliary_content_is_accepted(self):
        samples = {
            "docprops/app.xml": f'<Properties xmlns="{AP}"><Application>Microsoft Excel</Application></Properties>',
            "docprops/core.xml": '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Report</dc:title></cp:coreProperties>',
            "xl/styles.xml": f'<styleSheet xmlns="{SPREADSHEET}"><fonts count="1"><font/></fonts><fills count="1"><fill/></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="1"><xf/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles count="0"/></styleSheet>',
            "xl/theme/theme1.xml": '<a:theme xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" name="Office"><a:themeElements/></a:theme>',
        }
        for path, xml in samples.items():
            with self.subTest(path=path):
                root = ElementTree.fromstring(xml)
                validate_auxiliary_content(path, root)

    def test_unknown_auxiliary_namespace_is_rejected(self):
        root = ElementTree.fromstring('<Properties xmlns="urn:unexpected"><Application>X</Application></Properties>')
        with self.assertRaises(XlsxInspectionError) as error:
            validate_auxiliary_content("docprops/app.xml", root)
        self.assertEqual(error.exception.code, "XLSX_AUXILIARY_CONTENT_UNMODELED")


if __name__ == "__main__":
    unittest.main()
