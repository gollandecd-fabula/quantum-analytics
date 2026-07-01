from __future__ import annotations

from ._admission_contracts import (
    AdmissionDecision,
    AdmissionError,
    DatasetAdmissionRecord,
    DatasetAdmissionState,
    DatasetControlEvidence,
    DatasetDeclaration,
    DatasetSensitivity,
    StorageControlEvidence,
)
from ._admission_decisions import _AdmissionDecisionMixin
from ._admission_registry_base import _AdmissionRegistryBase
from ._admission_validation import _AdmissionValidationMixin


class RealDatasetAdmissionRegistry(
    _AdmissionValidationMixin,
    _AdmissionDecisionMixin,
    _AdmissionRegistryBase,
):
    """Thread-safe P1.6 admission state machine.

    The registry stores declarations and privacy-safe inspection metadata only.
    Raw commercial bytes are inspected in memory and are never retained here.
    """


__all__ = [
    "AdmissionDecision",
    "AdmissionError",
    "DatasetAdmissionRecord",
    "DatasetAdmissionState",
    "DatasetControlEvidence",
    "DatasetDeclaration",
    "DatasetSensitivity",
    "RealDatasetAdmissionRegistry",
    "StorageControlEvidence",
]
