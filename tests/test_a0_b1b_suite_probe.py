import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class B1bFullSuiteProbe(unittest.TestCase):
    def test_full_suite_probe(self):
        if os.environ.get("B1B_FULL_SUITE_PROBE")=="1":
            self.skipTest("nested probe disabled")
        env=dict(os.environ)
        env["B1B_FULL_SUITE_PROBE"]="1"
        env["PYTHONPATH"]="src"
        result=subprocess.run(
            [sys.executable,"-m","unittest","discover","-s","tests","-t","."],
            cwd=ROOT,env=env,text=True,capture_output=True,check=False,
        )
        output=(result.stdout+"\n"+result.stderr)[-12000:]
        print("B1B_SUITE_PROBE_TAIL="+output,flush=True)
        self.assertEqual(result.returncode,0,output)
