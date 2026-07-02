from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
import hmac
from typing import Any

from quantum.access import TenantContext


class LocalPilotExecutionError(ValueError):
    """Fail-closed local-pilot orchestration error with a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LocalPilotScope:
    host: str
    port: int
    operator_id: str
    organization_id: str
    tenant_id: str
    account_id: str
    read_only: bool = True
    single_operator: bool = True
    single_organization: bool = True
    marketplace_write_enabled: bool = False
    production_credentials_enabled: bool = False
    public_hosting_enabled: bool = False

    def validate(self, tenant: TenantContext) -> None:
        if self.host != "127.0.0.1":
            raise LocalPilotExecutionError("PILOT_LOOPBACK_REQUIRED")
        if (
            not isinstance(self.port, int)
            or isinstance(self.port, bool)
            or not (1 <= self.port <= 65535)
        ):
            raise LocalPilotExecutionError("PILOT_PORT_INVALID")
        for value, code in (
            (self.operator_id, "PILOT_OPERATOR_ID_INVALID"),
            (self.organization_id, "PILOT_ORGANIZATION_ID_INVALID"),
            (self.tenant_id, "PILOT_TENANT_ID_INVALID"),
            (self.account_id, "PILOT_ACCOUNT_ID_INVALID"),
        ):
            if not isinstance(value, str) or not value:
                raise LocalPilotExecutionError(code)
        if not self.read_only:
            raise LocalPilotExecutionError("PILOT_READ_ONLY_REQUIRED")
        if not self.single_operator:
            raise LocalPilotExecutionError("PILOT_SINGLE_OPERATOR_REQUIRED")
        if not self.single_organization:
            raise LocalPilotExecutionError("PILOT_SINGLE_ORGANIZATION_REQUIRED")
        if self.marketplace_write_enabled:
            raise LocalPilotExecutionError("PILOT_MARKETPLACE_WRITES_FORBIDDEN")
        if self.production_credentials_enabled:
            raise LocalPilotExecutionError("PILOT_PRODUCTION_CREDENTIALS_FORBIDDEN")
        if self.public_hosting_enabled:
            raise LocalPilotExecutionError("PILOT_PUBLIC_HOSTING_FORBIDDEN")
        if not isinstance(tenant, TenantContext):
            raise LocalPilotExecutionError("PILOT_TENANT_CONTEXT_REQUIRED")
        if not hmac.compare_digest(
            self.tenant_id,
            tenant.tenant_id,
        ) or not hmac.compare_digest(self.account_id, tenant.account_id):
            raise LocalPilotExecutionError("PILOT_TENANT_SCOPE_MISMATCH")


def require_aware(value: datetime, code: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise LocalPilotExecutionError(code)


def validate_time_order(
    observed_at: datetime,
    admitted_at: datetime,
    reconciled_at: datetime,
) -> None:
    if observed_at > admitted_at or admitted_at > reconciled_at:
        raise LocalPilotExecutionError("PILOT_TIMESTAMP_ORDER_INVALID")


def scope_matches_declaration(
    scope: LocalPilotScope,
    declaration: object,
) -> bool:
    tenant_id = getattr(declaration, "tenant_id", None)
    uploader_account_id = getattr(declaration, "uploader_account_id", None)
    return (
        isinstance(tenant_id, str)
        and isinstance(uploader_account_id, str)
        and hmac.compare_digest(scope.tenant_id, tenant_id)
        and hmac.compare_digest(scope.account_id, uploader_account_id)
    )


def _parse_request_time(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise LocalPilotExecutionError("PILOT_FINANCE_TIMESTAMP_INVALID")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise LocalPilotExecutionError(
            "PILOT_FINANCE_TIMESTAMP_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LocalPilotExecutionError("PILOT_FINANCE_TIMESTAMP_INVALID")
    return parsed


def validate_finance_request(
    label: str,
    request: object,
    scope: LocalPilotScope,
    *,
    admitted_at: datetime,
    reconciled_at: datetime,
) -> Mapping[str, Any]:
    if not isinstance(label, str) or not label:
        raise LocalPilotExecutionError("PILOT_FINANCE_LABEL_INVALID")
    if not isinstance(request, Mapping):
        raise LocalPilotExecutionError("PILOT_FINANCE_REQUEST_INVALID")
    organization_id = request.get("organization_id")
    if not isinstance(organization_id, str) or not hmac.compare_digest(
        organization_id,
        scope.organization_id,
    ):
        raise LocalPilotExecutionError(
            "PILOT_FINANCE_ORGANIZATION_MISMATCH"
        )
    if request.get("mode") != "ACTUAL" or request.get("scenario_id") is not None:
        raise LocalPilotExecutionError("PILOT_ACTUAL_MODE_REQUIRED")
    calculated_at = _parse_request_time(request.get("calculated_at"))
    if calculated_at < admitted_at or calculated_at > reconciled_at:
        raise LocalPilotExecutionError(
            "PILOT_FINANCE_TIMESTAMP_OUT_OF_RANGE"
        )
    return request


__all__ = [
    "LocalPilotExecutionError",
    "LocalPilotScope",
    "require_aware",
    "scope_matches_declaration",
    "validate_finance_request",
    "validate_time_order",
]
