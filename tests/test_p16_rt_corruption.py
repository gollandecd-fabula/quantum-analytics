import unittest
from struct import pack, unpack
from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamCorruptionTests(unittest.TestCase):
    def test_corrupted_deflate_stream_has_stable_code(self):
        payload = bytearray(build_xlsx())
        with ZipFile(BytesIO(payload)) as archive:
            info = archive.getinfo("[Content_Types].xml")
            offset = info.header_offset
        filename_length = unpack("<H", payload[offset + 26 : offset + 28])[0]
        extra_length = unpack("<H", payload[offset + 28 : offset + 30])[0]
        data_start = offset + 30 + filename_length + extra_length
        payload[data_start + max(1, info.compress_size // 2)] ^= 0xFF
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=bytes(payload), policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_READ_FAILED")

    def test_unsupported_zip_version_has_stable_code(self):
        payload = bytearray(build_xlsx())
        local_header = payload.find(b"PK\x03\x04")
        central_header = payload.find(b"PK\x01\x02")
        payload[local_header + 4 : local_header + 6] = pack("<H", 89)
        payload[central_header + 6 : central_header + 8] = pack("<H", 89)
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=bytes(payload), policy=policy())
        self.assertIn(error.exception.code, {"XLSX_ARCHIVE_INVALID", "XLSX_ARCHIVE_READ_FAILED"})


if __name__ == "__main__":
    unittest.main()
