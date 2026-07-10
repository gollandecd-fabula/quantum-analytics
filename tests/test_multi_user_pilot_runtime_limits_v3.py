from __future__ import annotations

import tests.test_multi_user_pilot_runtime_limits as _limits
from quantum.pilot.runtime_v3 import PilotIdentityRuntime


class PilotRuntimeV3LimitTests(_limits.PilotRuntimeLimitTests):
    def runtime(self, **limit_overrides) -> PilotIdentityRuntime:
        return PilotIdentityRuntime(
            hasher=_limits.Argon2idTestDouble(),
            limits=_limits.PilotRuntimeLimits(**limit_overrides),
        )
