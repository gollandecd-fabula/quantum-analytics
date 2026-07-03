from __future__ import annotations

from quantum.access import TenantContext

from ._manifest_common import boolean, exact_keys, integer, mapping, text
from ._scope import LocalPilotScope

_SCOPE_FIELDS = {
    "host",
    "port",
    "operator_id",
    "organization_id",
    "tenant_id",
    "account_id",
    "read_only",
    "single_operator",
    "single_organization",
    "marketplace_write_enabled",
    "production_credentials_enabled",
    "public_hosting_enabled",
}


def build_scope(value: object) -> tuple[LocalPilotScope, TenantContext]:
    item = mapping(value, "PILOT_SCOPE_INVALID")
    exact_keys(item, _SCOPE_FIELDS, "PILOT_SCOPE_INVALID")
    scope = LocalPilotScope(
        host=text(item["host"], "PILOT_SCOPE_INVALID", safe=False),
        port=integer(item["port"], "PILOT_SCOPE_INVALID", minimum=1),
        operator_id=text(item["operator_id"], "PILOT_SCOPE_INVALID"),
        organization_id=text(item["organization_id"], "PILOT_SCOPE_INVALID"),
        tenant_id=text(item["tenant_id"], "PILOT_SCOPE_INVALID"),
        account_id=text(item["account_id"], "PILOT_SCOPE_INVALID"),
        read_only=boolean(item["read_only"], "PILOT_SCOPE_INVALID"),
        single_operator=boolean(item["single_operator"], "PILOT_SCOPE_INVALID"),
        single_organization=boolean(
            item["single_organization"],
            "PILOT_SCOPE_INVALID",
        ),
        marketplace_write_enabled=boolean(
            item["marketplace_write_enabled"],
            "PILOT_SCOPE_INVALID",
        ),
        production_credentials_enabled=boolean(
            item["production_credentials_enabled"],
            "PILOT_SCOPE_INVALID",
        ),
        public_hosting_enabled=boolean(
            item["public_hosting_enabled"],
            "PILOT_SCOPE_INVALID",
        ),
    )
    tenant = TenantContext(scope.tenant_id, scope.account_id)
    scope.validate(tenant)
    return scope, tenant


__all__ = ["build_scope"]
