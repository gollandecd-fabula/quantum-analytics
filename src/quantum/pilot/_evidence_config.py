from __future__ import annotations

from dataclasses import dataclass

from ._manifest_common import boolean, exact_keys, mapping, sha256_text, text

_FIELDS = {
    "dataset_evidence_id",
    "dataset_verifier_account_id",
    "source_authority_verified",
    "report_period_verified",
    "control_totals_verified",
    "direct_identifiers_absent_or_approved",
    "malware_scan_clean",
    "malware_scan_evidence_sha256",
    "storage_evidence_id",
    "storage_verifier_account_id",
    "loopback_only",
    "transport_encrypted",
    "encryption_at_rest",
    "tenant_scoped_paths",
    "immutable_original",
    "separated_quarantine_and_admitted_zones",
    "least_privilege_credentials",
}


@dataclass(frozen=True, slots=True)
class EvidenceConfig:
    dataset_evidence_id: str
    dataset_verifier_account_id: str
    source_authority_verified: bool
    report_period_verified: bool
    control_totals_verified: bool
    direct_identifiers_absent_or_approved: bool
    malware_scan_clean: bool
    malware_scan_evidence_sha256: str
    storage_evidence_id: str
    storage_verifier_account_id: str
    loopback_only: bool
    transport_encrypted: bool
    encryption_at_rest: bool
    tenant_scoped_paths: bool
    immutable_original: bool
    separated_quarantine_and_admitted_zones: bool
    least_privilege_credentials: bool


def build_evidence_config(value: object) -> EvidenceConfig:
    item = mapping(value, "PILOT_EVIDENCE_CONFIG_INVALID")
    exact_keys(item, _FIELDS, "PILOT_EVIDENCE_CONFIG_INVALID")
    return EvidenceConfig(
        dataset_evidence_id=text(item["dataset_evidence_id"], "PILOT_EVIDENCE_CONFIG_INVALID"),
        dataset_verifier_account_id=text(
            item["dataset_verifier_account_id"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        source_authority_verified=boolean(
            item["source_authority_verified"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        report_period_verified=boolean(
            item["report_period_verified"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        control_totals_verified=boolean(
            item["control_totals_verified"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        direct_identifiers_absent_or_approved=boolean(
            item["direct_identifiers_absent_or_approved"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        malware_scan_clean=boolean(
            item["malware_scan_clean"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        malware_scan_evidence_sha256=sha256_text(
            item["malware_scan_evidence_sha256"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        storage_evidence_id=text(item["storage_evidence_id"], "PILOT_EVIDENCE_CONFIG_INVALID"),
        storage_verifier_account_id=text(
            item["storage_verifier_account_id"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        loopback_only=boolean(item["loopback_only"], "PILOT_EVIDENCE_CONFIG_INVALID"),
        transport_encrypted=boolean(
            item["transport_encrypted"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        encryption_at_rest=boolean(
            item["encryption_at_rest"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        tenant_scoped_paths=boolean(
            item["tenant_scoped_paths"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        immutable_original=boolean(
            item["immutable_original"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        separated_quarantine_and_admitted_zones=boolean(
            item["separated_quarantine_and_admitted_zones"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
        least_privilege_credentials=boolean(
            item["least_privilege_credentials"],
            "PILOT_EVIDENCE_CONFIG_INVALID",
        ),
    )


__all__ = ["EvidenceConfig", "build_evidence_config"]
