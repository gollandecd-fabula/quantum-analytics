from __future__ import annotations

import base64
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _surface(text: str) -> str:
    decoded = [
        base64.b64decode(value, validate=True).decode("utf-8")
        for value in re.findall(r'-Encoded\s+["\']([A-Za-z0-9+/=]{16,})["\']', text)
    ]
    return text + "\n" + "\n".join(decoded)
PILOT = ROOT / "src" / "quantum" / "pilot"
WINDOWS = ROOT / "scripts" / "windows"


class WindowsHashCompatR4Tests(unittest.TestCase):
    def test_hash_shim_implements_file_and_stream_sha256(self):
        script = (PILOT / "hash_compat.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-Command -Name Get-FileHash", script)
        self.assertIn("System.Security.Cryptography.SHA256", script)
        self.assertIn('ParameterSetName = "LiteralPath"', script)
        self.assertIn('ParameterSetName = "InputStream"', script)
        self.assertIn("ComputeHash", script)

    def test_front_door_loads_shim_before_scan_receipt_execution(self):
        script = (WINDOWS / "import_source.ps1").read_text(encoding="utf-8")
        load = script.index(". $hashCompat")
        execution = script.index("$scanReceipt = New-ScanReceipt", load)
        self.assertLess(load, execution)
        self.assertIn("Get-FileHash", script)
        self.assertIn("Модуль совместимости SHA-256 Quantum не найден", _surface(script))

    def test_xlsx_helper_loads_shim_before_scan_receipt_execution(self):
        script = (PILOT / "import_xlsx_source.ps1").read_text(encoding="utf-8")
        load = script.index(". $hashCompat")
        execution = script.index("$scanReceipt = Resolve-ScanReceipt", load)
        self.assertLess(load, execution)
        self.assertIn("Get-FileHash", script)
        self.assertIn("Модуль совместимости SHA-256 Quantum не найден", _surface(script))

    def test_compatibility_scripts_are_ascii_for_windows_powershell(self):
        for path in (
            PILOT / "hash_compat.ps1",
            WINDOWS / "import_source.ps1",
            PILOT / "import_xlsx_source.ps1",
        ):
            payload = path.read_bytes()
            self.assertEqual(payload.decode("ascii").encode("ascii"), payload)


if __name__ == "__main__":
    unittest.main()
