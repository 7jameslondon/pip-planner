from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_cli_writes_json_and_two_svg_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_planner",
                    "design",
                    "GTAC",
                    "--architecture",
                    "hairpin",
                    "--out",
                    tmp,
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=20,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["recognition_pairs"], ["Im/Py", "Hp/Py", "Py/Hp", "Py/Im"])

            chemical = Path(payload["files"]["chemical_svg"])
            schematic = Path(payload["files"]["schematic_svg"])
            design_json = Path(payload["files"]["json"])
            self.assertTrue(chemical.exists())
            self.assertTrue(schematic.exists())
            self.assertTrue(design_json.exists())
            self.assertIn("<svg", chemical.read_text(encoding="utf-8"))
            self.assertIn("data-renderer=\"RDKit\"", chemical.read_text(encoding="utf-8"))
            self.assertIn("PIP schematic", schematic.read_text(encoding="utf-8"))
            self.assertTrue(payload["chemical_renderer"].startswith("RDKit "))
            self.assertIn("chemical_smiles", payload)
            self.assertIn("C(=O)", payload["chemical_smiles"])

    def test_cli_rejects_invalid_sequence(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "pip_planner", "design", "GTX"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("Invalid character", completed.stderr)

    def test_cli_accepts_sequence_without_subcommand(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_planner",
                    "GTAC",
                    "--out",
                    tmp,
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=20,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["sequence"], "GTAC")


if __name__ == "__main__":
    unittest.main()
