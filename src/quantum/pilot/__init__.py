from . import local_runner as _local_runner
from .reconciliation_guard import install as _install_reconciliation_guard
from .windows_runner import install_windows_compatibility
from .windows_storage_compat import install_windows_storage_compatibility

LocalPilotError, run_local_pilot = _install_reconciliation_guard(_local_runner)

install_windows_compatibility()
install_windows_storage_compatibility()

__all__ = [
    "LocalPilotError",
    "install_windows_compatibility",
    "install_windows_storage_compatibility",
    "run_local_pilot",
]
