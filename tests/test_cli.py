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
            chemical_svg = chemical.read_text(encoding="utf-8")
            self.assertIn("<svg", chemical_svg)
            self.assertIn("data-renderer=\"RDKit\"", chemical_svg)
            self.assertNotIn("#FF0000", chemical_svg)
            self.assertNotIn("#0000FF", chemical_svg)
            self.assertNotIn("stroke:#FF0000", chemical_svg)
            self.assertNotIn("stroke:#0000FF", chemical_svg)
            schematic_svg = schematic.read_text(encoding="utf-8")
            self.assertIn("PIP schematic", schematic_svg)
            self.assertIn('data-schematic="polyamide-figure"', schematic_svg)
            self.assertIn('data-legend="polyamide-symbols"', schematic_svg)
            self.assertIn('class="monomer im-symbol"', schematic_svg)
            self.assertIn('class="monomer py-symbol"', schematic_svg)
            self.assertIn('class="monomer hp-symbol"', schematic_svg)
            self.assertIn("\u03b3", schematic_svg)
            self.assertNotIn(">Sequence<", schematic_svg)
            self.assertNotIn("short recognition sites", schematic_svg)
            self.assertTrue(payload["chemical_renderer"].startswith("RDKit "))
            self.assertIn("chemical_smiles", payload)
            self.assertIn("C(=O)", payload["chemical_smiles"])
            solubility_methods = {prediction["method"] for prediction in payload["solubility_predictions"]}
            self.assertEqual(solubility_methods, {"ADMET-AI v2", "SolTranNet"})

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
