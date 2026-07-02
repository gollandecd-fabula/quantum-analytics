from __future__ import annotations

from ._xlsx_content_model import validate_modeled_xml_content
from ._xlsx_contracts import XlsxInspectionLimits


def validate_hidden_xml_content(
    workbook: bytes,
    limits: XlsxInspectionLimits,
):
    return validate_modeled_xml_content(workbook, limits)


__all__ = ["validate_hidden_xml_content"]
