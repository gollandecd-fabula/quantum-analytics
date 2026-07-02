from __future__ import annotations

from io import BytesIO
from zipfile import BadZipFile, ZipFile, ZipInfo
from zlib import error as ZlibError

from ._xlsx_contracts import XlsxInspectionError

_LOCAL_HEADER = b"PK\x03\x04"
_CENTRAL_HEADER = b"PK\x01\x02"
_DATA_DESCRIPTOR = b"PK\x07\x08"
_END_RECORD = b"PK\x05\x06"
_END_RECORD_SIZE = 22
_MAX_COMMENT_SIZE = 65535
_LOCAL_FIXED_SIZE = 30
_CENTRAL_FIXED_SIZE = 46


def _u16(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 2], "little")


def _u32(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 4], "little")


def _u64(payload: bytes, offset: int) -> int:
    return int.from_bytes(payload[offset : offset + 8], "little")


def _end_record_offset(payload: bytes) -> int:
    search_start = max(
        0,
        len(payload) - (_END_RECORD_SIZE + _MAX_COMMENT_SIZE),
    )
    cursor = len(payload)
    while cursor > search_start:
        offset = payload.rfind(_END_RECORD, search_start, cursor)
        if offset < 0:
            break
        if offset + _END_RECORD_SIZE <= len(payload):
            comment_size = _u16(payload, offset + 20)
            if offset + _END_RECORD_SIZE + comment_size == len(payload):
                if comment_size:
                    raise XlsxInspectionError(
                        "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN"
                    )
                return offset
        cursor = offset
    raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")


def _validate_central_directory(
    payload: bytes,
    *,
    offset: int,
    size: int,
    entry_count: int,
    end_record_offset: int,
) -> None:
    cursor = offset
    for _ in range(entry_count):
        if (
            cursor + _CENTRAL_FIXED_SIZE > end_record_offset
            or payload[cursor : cursor + 4] != _CENTRAL_HEADER
        ):
            raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
        name_size = _u16(payload, cursor + 28)
        extra_size = _u16(payload, cursor + 30)
        comment_size = _u16(payload, cursor + 32)
        if comment_size:
            raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
        cursor += _CENTRAL_FIXED_SIZE + name_size + extra_size
    if cursor != offset + size or cursor != end_record_offset:
        raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")


def _descriptor_matches(payload: bytes, info: ZipInfo) -> bool:
    layouts = (
        (False, 4),
        (True, 4),
        (False, 8),
        (True, 8),
    )
    for has_signature, size_width in layouts:
        expected_size = (4 if has_signature else 0) + 4 + 2 * size_width
        if len(payload) != expected_size:
            continue
        cursor = 0
        if has_signature:
            if payload[:4] != _DATA_DESCRIPTOR:
                continue
            cursor = 4
        crc = _u32(payload, cursor)
        cursor += 4
        if size_width == 4:
            compressed = _u32(payload, cursor)
            uncompressed = _u32(payload, cursor + 4)
        else:
            compressed = _u64(payload, cursor)
            uncompressed = _u64(payload, cursor + 8)
        if (
            crc == info.CRC
            and compressed == info.compress_size
            and uncompressed == info.file_size
        ):
            return True
    return False


def _expected_local_name(info: ZipInfo, flags: int) -> bytes:
    encoding = "utf-8" if flags & 0x800 else "cp437"
    try:
        return info.orig_filename.encode(encoding)
    except UnicodeEncodeError as exc:
        raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN") from exc


def _validate_local_records(
    payload: bytes,
    infos: list[ZipInfo],
    central_directory_offset: int,
) -> None:
    if not infos:
        raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
    ordered = sorted(infos, key=lambda info: info.header_offset)
    cursor = 0
    for index, info in enumerate(ordered):
        offset = info.header_offset
        next_offset = (
            ordered[index + 1].header_offset
            if index + 1 < len(ordered)
            else central_directory_offset
        )
        if (
            offset != cursor
            or offset + _LOCAL_FIXED_SIZE > next_offset
            or payload[offset : offset + 4] != _LOCAL_HEADER
        ):
            raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
        flags = _u16(payload, offset + 6)
        compression = _u16(payload, offset + 8)
        local_crc = _u32(payload, offset + 14)
        local_compressed = _u32(payload, offset + 18)
        local_uncompressed = _u32(payload, offset + 22)
        name_size = _u16(payload, offset + 26)
        extra_size = _u16(payload, offset + 28)
        name_start = offset + _LOCAL_FIXED_SIZE
        data_start = name_start + name_size + extra_size
        data_end = data_start + info.compress_size
        if (
            flags != info.flag_bits
            or compression != info.compress_type
            or data_start > next_offset
            or data_end > next_offset
            or payload[name_start : name_start + name_size]
            != _expected_local_name(info, flags)
        ):
            raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
        if flags & 0x08:
            if not _descriptor_matches(payload[data_end:next_offset], info):
                raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
        elif (
            data_end != next_offset
            or local_crc != info.CRC
            or local_compressed != info.compress_size
            or local_uncompressed != info.file_size
        ):
            raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
        cursor = next_offset
    if cursor != central_directory_offset:
        raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")


def validate_zip_record_coverage(payload: bytes) -> None:
    if not isinstance(payload, bytes) or not payload.startswith(_LOCAL_HEADER):
        raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
    try:
        with ZipFile(BytesIO(payload)) as zf:
            end_record_offset = _end_record_offset(payload)
            if (
                _u16(payload, end_record_offset + 4) != 0
                or _u16(payload, end_record_offset + 6) != 0
            ):
                raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
            entries_on_disk = _u16(payload, end_record_offset + 8)
            entry_count = _u16(payload, end_record_offset + 10)
            central_size = _u32(payload, end_record_offset + 12)
            central_offset = _u32(payload, end_record_offset + 16)
            if (
                entries_on_disk == 0xFFFF
                or entry_count == 0xFFFF
                or central_size == 0xFFFFFFFF
                or central_offset == 0xFFFFFFFF
                or entries_on_disk != entry_count
                or entry_count != len(zf.infolist())
                or central_offset != zf.start_dir
                or central_offset + central_size != end_record_offset
            ):
                raise XlsxInspectionError("XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")
            _validate_central_directory(
                payload,
                offset=central_offset,
                size=central_size,
                entry_count=entry_count,
                end_record_offset=end_record_offset,
            )
            _validate_local_records(payload, zf.infolist(), central_offset)
    except XlsxInspectionError:
        raise
    except (
        BadZipFile,
        NotImplementedError,
        ValueError,
        OSError,
        EOFError,
        ZlibError,
    ) as exc:
        raise XlsxInspectionError("XLSX_ARCHIVE_INVALID") from exc


__all__ = ["validate_zip_record_coverage"]
