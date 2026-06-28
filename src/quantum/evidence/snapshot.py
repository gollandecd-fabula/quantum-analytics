from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from quantum.domain.states import DataState, TypedValue

from .canonical import datetime_text, freeze_json, jsonable, require_aware, require_text, sha256_hex
from .evidence_chain import EvidenceChain
from .references import (
    CalculationMode,
    EvidenceValidity,
    RecalculationAudit,
    VersionedRef,
)


def _typed_value_document(value: TypedValue) -> dict[str, Any]:
    return {
        "state": value.state.value,
        "value": jsonable(value.value),
        "value_type": value.value_type,
        "unit": value.unit,
        "reason_code": value.reason_code,
        "source_record_id": value.source_record_id,
        "observed_at": jsonable(value.observed_at),
        "metadata": jsonable(value.metadata),
    }


def _reproduction_material(document: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "result_contract_version",
        "evidence_contract_version",
        "organization_id",
        "marketplace_account_id",
        "mode",
        "scenario_id",
        "calculation_instant",
        "scope_dimensions",
        "calculation_profile_ref",
        "metric_definition_ref",
        "value",
        "evidence_chain",
    )
    return {key: document[key] for key in keys}


def compute_document_hashes(document: Mapping[str, Any]) -> tuple[str, str, str]:
    reproduction_hash = sha256_hex(_reproduction_material(document))
    content_material = {
        **_reproduction_material(document),
        "audit": document["audit"],
    }
    content_hash = sha256_hex(content_material)
    return reproduction_hash, content_hash, f"mr_{content_hash}"


def verify_document_hashes(document: Mapping[str, Any]) -> None:
    reproduction_hash, content_hash, result_id = compute_document_hashes(document)
    if document.get("reproduction_hash") != reproduction_hash:
        raise ValueError("Metric result reproduction_hash mismatch.")
    if document.get("content_hash") != content_hash:
        raise ValueError("Metric result content_hash mismatch.")
    if document.get("result_id") != result_id:
        raise ValueError("Metric result result_id mismatch.")


@dataclass(frozen=True, slots=True)
class MetricResultSnapshot:
    result_id: str
    result_contract_version: str
    evidence_contract_version: str
    organization_id: str
    marketplace_account_id: str | None
    mode: CalculationMode
    scenario_id: str | None
    calculation_instant: datetime
    scope_dimensions: Mapping[str, str]
    calculation_profile_ref: VersionedRef
    metric_definition_ref: VersionedRef
    value: TypedValue
    evidence_chain: EvidenceChain
    audit: RecalculationAudit
    reproduction_hash: str
    content_hash: str

    @classmethod
    def build(
        cls,
        *,
        organization_id: str,
        marketplace_account_id: str | None,
        mode: CalculationMode,
        scenario_id: str | None,
        calculation_instant: datetime,
        scope_dimensions: Mapping[str, str],
        calculation_profile_ref: VersionedRef,
        metric_definition_ref: VersionedRef,
        value: TypedValue,
        evidence_chain: EvidenceChain,
        audit: RecalculationAudit,
        result_contract_version: str = "METRIC-RESULT-v1",
        evidence_contract_version: str = "EVIDENCE-CHAIN-v1",
    ) -> "MetricResultSnapshot":
        require_text(organization_id, "MetricResultSnapshot.organization_id")
        require_aware(calculation_instant, "MetricResultSnapshot.calculation_instant")
        if marketplace_account_id is not None:
            require_text(marketplace_account_id, "MetricResultSnapshot.marketplace_account_id")
        if mode is CalculationMode.ACTUAL:
            if scenario_id is not None:
                raise ValueError("ACTUAL metric result must have scenario_id=None.")
        elif not scenario_id:
            raise ValueError("SCENARIO metric result requires scenario_id.")

        normalized_scope = dict(scope_dimensions)
        if any(
            not isinstance(key, str)
            or not key
            or not isinstance(item, str)
            or not item
            for key, item in normalized_scope.items()
        ):
            raise ValueError("scope_dimensions require non-empty string keys and values.")

        frozen_value = TypedValue(
            state=value.state,
            value=freeze_json(value.value),
            value_type=value.value_type,
            unit=value.unit,
            reason_code=value.reason_code,
            source_record_id=value.source_record_id,
            observed_at=value.observed_at,
            metadata=freeze_json(value.metadata),
        )
        if evidence_chain.organization_id != organization_id:
            raise ValueError("Metric result and Evidence Chain organization mismatch.")
        if evidence_chain.marketplace_account_id != marketplace_account_id:
            raise ValueError("Metric result and Evidence Chain account mismatch.")
        if evidence_chain.calculation_profile_ref != calculation_profile_ref:
            raise ValueError("Calculation Profile reference mismatch.")
        if evidence_chain.metric_definition_ref != metric_definition_ref:
            raise ValueError("Metric definition reference mismatch.")
        if (
            frozen_value.state is DataState.VALID
            and evidence_chain.validity.status is not EvidenceValidity.VERIFIED
        ):
            raise ValueError("VALID metric result requires VERIFIED evidence.")
        if frozen_value.source_record_id is not None:
            source_ids = {item.source_record_id for item in evidence_chain.source_records}
            if frozen_value.source_record_id not in source_ids:
                raise ValueError("Typed value source_record_id is not present in Evidence Chain.")
        if audit.calculated_at < calculation_instant:
            raise ValueError("calculated_at cannot precede calculation_instant.")

        base_document = {
            "result_contract_version": result_contract_version,
            "evidence_contract_version": evidence_contract_version,
            "organization_id": organization_id,
            "marketplace_account_id": marketplace_account_id,
            "mode": mode.value,
            "scenario_id": scenario_id,
            "calculation_instant": datetime_text(calculation_instant),
            "scope_dimensions": normalized_scope,
            "calculation_profile_ref": jsonable(calculation_profile_ref),
            "metric_definition_ref": jsonable(metric_definition_ref),
            "value": _typed_value_document(frozen_value),
            "evidence_chain": jsonable(evidence_chain),
            "audit": jsonable(audit),
        }
        reproduction_hash, content_hash, result_id = compute_document_hashes(base_document)
        return cls(
            result_id=result_id,
            result_contract_version=result_contract_version,
            evidence_contract_version=evidence_contract_version,
            organization_id=organization_id,
            marketplace_account_id=marketplace_account_id,
            mode=mode,
            scenario_id=scenario_id,
            calculation_instant=calculation_instant,
            scope_dimensions=MappingProxyType(normalized_scope),
            calculation_profile_ref=calculation_profile_ref,
            metric_definition_ref=metric_definition_ref,
            value=frozen_value,
            evidence_chain=evidence_chain,
            audit=audit,
            reproduction_hash=reproduction_hash,
            content_hash=content_hash,
        )

    def to_document(self) -> dict[str, Any]:
        document = {
            "result_id": self.result_id,
            "result_contract_version": self.result_contract_version,
            "evidence_contract_version": self.evidence_contract_version,
            "organization_id": self.organization_id,
            "marketplace_account_id": self.marketplace_account_id,
            "mode": self.mode.value,
            "scenario_id": self.scenario_id,
            "calculation_instant": datetime_text(self.calculation_instant),
            "scope_dimensions": dict(self.scope_dimensions),
            "calculation_profile_ref": jsonable(self.calculation_profile_ref),
            "metric_definition_ref": jsonable(self.metric_definition_ref),
            "value": _typed_value_document(self.value),
            "evidence_chain": jsonable(self.evidence_chain),
            "audit": jsonable(self.audit),
            "reproduction_hash": self.reproduction_hash,
            "content_hash": self.content_hash,
        }
        verify_document_hashes(document)
        return document
