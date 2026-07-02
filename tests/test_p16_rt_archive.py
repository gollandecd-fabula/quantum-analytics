import unittest
from struct import pack
from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamArchiveTests(unittest.TestCase):
    def test_drive_like_outer_member_is_rejected(self):
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("C:/weekly.xlsx", build_xlsx())
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=buffer.getvalue(), policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_PATH_INVALID")

    def test_unicode_equivalent_paths_are_duplicates(self):
        source = build_xlsx()
        output = BytesIO()
        with ZipFile(BytesIO(source)) as current, ZipFile(output, "w", compression=ZIP_DEFLATED) as rewritten:
            for info in current.infolist():
                rewritten.writestr(info.filename, current.read(info))
            rewritten.writestr("custom/é.txt", b"a")
            rewritten.writestr("custom/e\u0301.txt", b"b")
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=output.getvalue(), policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_DUPLICATE_PATH")

    def test_unknown_compression_method_has_stable_code(self):
        payload = bytearray(build_xlsx())
        local_header = payload.find(b"PK\x03\x04")
        central_header = payload.find(b"PK\x01\x02")
        payload[local_header + 8 : local_header + 10] = pack("<H", 99)
        payload[central_header + 10 : central_header + 12] = pack("<H", 99)
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=bytes(payload), policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_COMPRESSION_UNSUPPORTED")


if __name__ == "__main__":
    unittest.main()
