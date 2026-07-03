from pathlib import Path
import json
import os
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
            complex_pdb = Path(payload["files"]["complex_pdb"])
            model_html = Path(payload["files"]["model_html"])
            design_json = Path(payload["files"]["json"])
            self.assertTrue(chemical.exists())
            self.assertTrue(schematic.exists())
            self.assertTrue(complex_pdb.exists())
            self.assertTrue(model_html.exists())
            self.assertTrue(design_json.exists())
            chemical_svg = chemical.read_text(encoding="utf-8")
            self.assertIn("<svg", chemical_svg)
            self.assertIn("data-renderer=\"RDKit\"", chemical_svg)
            self.assertNotIn("#FF0000", chemical_svg)
            self.assertNotIn("#0000FF", chemical_svg)
            self.assertNotIn("stroke:#FF0000", chemical_svg)
            self.assertNotIn("stroke:#0000FF", chemical_svg)
            self.assertNotIn("hairpin;", chemical_svg)
            self.assertNotIn("RDKit 2D depiction", chemical_svg)
            schematic_svg = schematic.read_text(encoding="utf-8")
            self.assertIn("PIP schematic", schematic_svg)
            self.assertIn('data-schematic="polyamide-figure"', schematic_svg)
            self.assertIn('data-legend="polyamide-symbols"', schematic_svg)
            self.assertEqual(schematic_svg.count('class="legend-item"'), 4)
            self.assertIn('class="monomer im-symbol"', schematic_svg)
            self.assertIn('class="monomer py-symbol"', schematic_svg)
            self.assertIn('class="monomer hp-symbol"', schematic_svg)
            self.assertIn('class="turn-symbol ink"', schematic_svg)
            self.assertIn("\u03b3", schematic_svg)
            self.assertNotIn(">Sequence<", schematic_svg)
            self.assertNotIn(">Polyamide<", schematic_svg)
            self.assertNotIn("hairpin;", schematic_svg)
            self.assertNotIn("A/T mode:", schematic_svg)
            self.assertNotIn("5&#x27;-", schematic_svg)
            self.assertNotIn("-3&#x27;", schematic_svg)
            self.assertNotIn("short recognition sites", schematic_svg)
            self.assertTrue(payload["chemical_renderer"].startswith("RDKit "))
            self.assertIn("chemical_smiles", payload)
            self.assertIn("C(=O)", payload["chemical_smiles"])
            solubility_methods = {prediction["method"] for prediction in payload["solubility_predictions"]}
            self.assertEqual(solubility_methods, {"ADMET-AI v2", "SolTranNet"})
            self.assertEqual(payload["genome_occurrences"]["status"], "skipped")
            self.assertEqual(payload["model_3d"]["dna_force_field"], "AMBER DNA.OL24")
            self.assertEqual(payload["model_3d"]["binder_force_field"], "GAFF2")
            self.assertIn(payload["model_3d"]["md_simulation"]["status"], {"not_run", "engine_available_not_run"})
            complex_text = complex_pdb.read_text(encoding="utf-8")
            self.assertIn("HETATM", complex_text)
            self.assertIn("AMBER DNA.OL24", complex_text)

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

    def test_cli_can_count_local_genome_occurrences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["PIP_PLANNER_GENOME_DIR"] = str(ROOT / "tests" / "fixtures" / "genomes")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_planner",
                    "design",
                    "ATGC",
                    "--out",
                    tmp,
                    "--format",
                    "json",
                    "--genome",
                    "human-grch38",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            genome = payload["genome_occurrences"]
            self.assertEqual(genome["status"], "ok")
            self.assertEqual(genome["total_occurrences"], 2)
            self.assertEqual(genome["total_possibilities"], 34)
            self.assertTrue(genome["locations_listed"])
            self.assertIn("GENE1", genome["locations"][0]["feature_summary"])

    def test_cli_lists_public_genomes_without_hela(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_planner",
                "genomes",
                "list",
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
        genomes = {genome["id"]: genome for genome in payload["genomes"]}
        self.assertIn("sacCer3", genomes)
        self.assertIn("human-grch38", genomes)
        self.assertNotIn("hela", genomes)
        self.assertTrue(genomes["sacCer3"]["available"])

    def test_cli_imports_custom_genome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "custom.fa"
            source.write_text(">chrCustom\nATGCATGC\n", encoding="utf-8")
            env = os.environ.copy()
            env["PIP_PLANNER_GENOME_DIR"] = str(root / "genomes")

            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_planner",
                    "genomes",
                    "import",
                    str(source),
                    "--label",
                    "Custom Genome",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "imported")
            self.assertEqual(payload["genome"]["id"], "custom-genome")

    def test_cli_deletes_custom_genome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "custom.fa"
            source.write_text(">chrCustom\nATGCATGC\n", encoding="utf-8")
            env = os.environ.copy()
            env["PIP_PLANNER_GENOME_DIR"] = str(root / "genomes")

            imported = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_planner",
                    "genomes",
                    "import",
                    str(source),
                    "--label",
                    "Custom Genome",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)

            deleted = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_planner",
                    "genomes",
                    "delete",
                    "custom-genome",
                    "--format",
                    "json",
                ],
                cwd=ROOT,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
            )

            self.assertEqual(deleted.returncode, 0, deleted.stderr)
            payload = json.loads(deleted.stdout)
            self.assertEqual(payload["status"], "deleted")
            self.assertFalse((root / "genomes" / "custom-genome" / "genome.fa").exists())

    def test_cli_can_generate_one_product_at_a_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            schematic = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_planner",
                    "design",
                    "ATGC",
                    "--out",
                    tmp,
                    "--format",
                    "json",
                    "--product",
                    "schematic",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(schematic.returncode, 0, schematic.stderr)
            schematic_payload = json.loads(schematic.stdout)
            self.assertEqual(schematic_payload["product"], "schematic")
            self.assertIn("schematic_svg", schematic_payload["files"])
            self.assertNotIn("chemical_svg", schematic_payload["files"])

            chemical = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip_planner",
                    "design",
                    "ATGC",
                    "--out",
                    tmp,
                    "--format",
                    "json",
                    "--product",
                    "chemical",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(chemical.returncode, 0, chemical.stderr)
            chemical_payload = json.loads(chemical.stdout)
            self.assertEqual(chemical_payload["product"], "chemical")
            self.assertIn("chemical_svg", chemical_payload["files"])
            self.assertIn("chemical_smiles", chemical_payload)


if __name__ == "__main__":
    unittest.main()
