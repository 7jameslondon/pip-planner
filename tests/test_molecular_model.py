from pathlib import Path
import tempfile
import unittest

from pip_planner.model import DesignOptions, design_polyamide
from pip_planner.molecular_model import build_molecular_model, render_pdb, write_molecular_model_files


class MolecularModelTests(unittest.TestCase):
    def test_builds_dna_polyamide_initial_model(self) -> None:
        design = design_polyamide("ATGC", DesignOptions(architecture="hairpin"))
        model = build_molecular_model(design, "CC")
        payload = model.to_dict()

        self.assertGreater(len(payload["atoms"]), 40)
        self.assertGreater(len(payload["bonds"]), 30)
        self.assertEqual(payload["metadata"]["dna_force_field"], "AMBER DNA.OL24")
        self.assertEqual(payload["metadata"]["binder_force_field"], "GAFF2")
        self.assertIn(payload["metadata"]["md_simulation"]["status"], {"not_run", "engine_available_not_run"})
        self.assertTrue(any(atom["group"] == "ligand" for atom in payload["atoms"]))
        self.assertTrue(any(atom["group"] == "dna" for atom in payload["atoms"]))

    def test_writes_pdb_json_html_and_protocol_files(self) -> None:
        design = design_polyamide("ATGC", DesignOptions(architecture="linear", tail="none"))
        with tempfile.TemporaryDirectory() as tmp:
            result = write_molecular_model_files(design, Path(tmp), "atgc-linear", "CC")

            files = result["model_3d"]["files"]
            for key in ("complex_pdb", "model_json", "model_html", "md_protocol"):
                self.assertTrue(Path(files[key]).exists(), key)

            pdb_text = Path(files["complex_pdb"]).read_text(encoding="utf-8")
            self.assertIn("PIP PLANNER DNA POLYAMIDE INITIAL MODEL", pdb_text)
            self.assertIn("HETATM", pdb_text)
            self.assertIn("CONECT", pdb_text)
            self.assertIn("AMBER DNA.OL24", pdb_text)

    def test_pdb_renderer_contains_dna_and_ligand_records(self) -> None:
        design = design_polyamide("GTAC")
        model = build_molecular_model(design, "CC")
        pdb_text = render_pdb(model)

        self.assertIn("ATOM", pdb_text)
        self.assertIn("HETATM", pdb_text)
        self.assertIn("MD STATUS", pdb_text)


if __name__ == "__main__":
    unittest.main()
