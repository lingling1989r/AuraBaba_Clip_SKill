import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "-m", "clipclipskill.cli"]


class SmokePipelineTests(unittest.TestCase):
    def test_doctor_runs(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        result = subprocess.run(CLI + ["doctor"], cwd=ROOT, env=env, capture_output=True, text=True, check=True)
        payload = json.loads(result.stdout)
        self.assertIn("ffmpeg", payload)


if __name__ == "__main__":
    unittest.main()
