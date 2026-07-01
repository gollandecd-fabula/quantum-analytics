import unittest
from struct import pack, unpack
from tests.p16_fixtures import *  # noqa: F403


def _corrupt_member(payload: bytes, member_name: str) -> bytes:
    corrupted = bytearray(payload)
    with ZipFile(BytesIO(corrupted)) as archive:
        info = archive.getinfo(member_name)
        offset = info.header_offset
    filename_length = unpack("<H", corrupted[offset + 26 : offset + 28])[0]
    extra_length = unpack("<H", corrupted[offset + 28 : offset + 30])[0]
    data_start = offset + 30 + filename_length + extra_length
    corrupted[data_start + info.compress_size // 2] ^= 0xFF
    return bytes(corrupted)


class P16RedTeamCorruptionTests(unittest.TestCase):
    def test_corrupted_deflate_stream_has_stable_code(self):
        payload = _corrupt_member(build_xlsx(), "[Content_Types].xml")
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_READ_FAILED")

    def test_corrupted_unreferenced_member_is_rejected(self):
        metadata = bytes(range(256)) * 4
        payload = build_xlsx(extra_entries={"docProps/core.xml": metadata})
        payload = _corrupt_member(payload, "docProps/core.xml")
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
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
