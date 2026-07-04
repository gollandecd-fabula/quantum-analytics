from .local_runner import LocalPilotError, run_local_pilot
from .windows_runner import install_windows_compatibility
from .windows_storage_compat import install_windows_storage_compatibility

install_windows_compatibility()
install_windows_storage_compatibility()

__all__ = [
    "LocalPilotError",
    "install_windows_compatibility",
    "install_windows_storage_compatibility",
    "run_local_pilot",
]
