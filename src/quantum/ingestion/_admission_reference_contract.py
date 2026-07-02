from __future__ import annotations

from . import _admission_contracts_v2 as contracts

_PLACEHOLDER = "schema-reference"
_PATCH_MARKER = "_quantum_schema_reference_contract_v1"


def _safe_reference(value: object, code: str, *, max_length: int = 160) -> str:
    if not isinstance(value, str):
        raise contracts.AdmissionError(code)
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        raise contracts.AdmissionError(code)
    return normalized


def apply_reference_contract() -> None:
    evidence_type = contracts.DatasetControlEvidence
    if getattr(evidence_type, _PATCH_MARKER, False):
        return
    original_post_init = evidence_type.__post_init__

    def compatible_post_init(self) -> None:
        original_values = (
            self.matched_schema_id,
            self.matched_schema_version,
            self.matched_schema_authority_reference,
        )
        object.__setattr__(self, "matched_schema_id", _PLACEHOLDER)
        object.__setattr__(self, "matched_schema_version", _PLACEHOLDER)
        object.__setattr__(
            self,
            "matched_schema_authority_reference",
            _PLACEHOLDER,
        )
        try:
            original_post_init(self)
        finally:
            object.__setattr__(self, "matched_schema_id", original_values[0])
            object.__setattr__(self, "matched_schema_version", original_values[1])
            object.__setattr__(
                self,
                "matched_schema_authority_reference",
                original_values[2],
            )
        _safe_reference(
            original_values[0],
            "DATASET_EVIDENCE_SCHEMA_ID_INVALID",
        )
        _safe_reference(
            original_values[1],
            "DATASET_EVIDENCE_SCHEMA_VERSION_INVALID",
        )
        _safe_reference(
            original_values[2],
            "DATASET_EVIDENCE_SCHEMA_AUTHORITY_INVALID",
        )

    evidence_type.__post_init__ = compatible_post_init
    setattr(evidence_type, _PATCH_MARKER, True)
