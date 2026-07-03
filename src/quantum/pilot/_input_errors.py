from quantum.ingestion.receipts import IngestionError
from quantum.ingestion.xlsx_inspection import XlsxInspectionError

INPUT_PILOT_ERRORS = (IngestionError, XlsxInspectionError)

__all__ = ["INPUT_PILOT_ERRORS"]
