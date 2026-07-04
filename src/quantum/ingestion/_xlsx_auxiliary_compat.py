from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from zlib import error as ZlibError

from ._xlsx_archive import _read_limited
from ._xlsx_contracts import XlsxInspectionError, XlsxInspectionLimits

_AUXILIARY_PARTS = frozenset(
    {
        "docprops/app.xml",
        "docprops/core.xml",
        "xl/styles.xml",
        "xl/theme/theme1.xml",
    }
)


def hash_unmodeled_auxiliary_parts(
    workbook: bytes,
    limits: XlsxInspectionLimits,
) -> tuple[tuple[str, str, int], ...]:
    """Hash-bind tolerated non-semantic Office metadata in HOME_LOCAL mode."""
    auxiliary: list[tuple[str, str, int]] = []
    try:
        with ZipFile(BytesIO(workbook)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                normalized = info.filename.replace("\\", "/").casefold()
                if normalized not in _AUXILIARY_PARTS:
                    continue
                payload = _read_limited(archive, info.filename, limits)
                auxiliary.append(
                    (
                        "compat-unmodeled:" + normalized,
                        sha256(payload).hexdigest(),
                        len(payload),
                    )
                )
        return tuple(sorted(auxiliary))
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


__all__ = ["hash_unmodeled_auxiliary_parts"]
