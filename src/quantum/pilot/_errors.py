from __future__ import annotations

from quantum.finance import FinanceError
from quantum.ingestion.admission import AdmissionError
from quantum.reconciliation import ReconciliationError

from ._scope import LocalPilotExecutionError

KNOWN_PILOT_ERRORS = (
    LocalPilotExecutionError,
    AdmissionError,
    FinanceError,
    ReconciliationError,
)


def error_code(error: BaseException) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, str) and code:
        return code
    return "PILOT_INTERNAL_ERROR"


__all__ = ["KNOWN_PILOT_ERRORS", "error_code"]
