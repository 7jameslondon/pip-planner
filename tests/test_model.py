import unittest

from pip_planner.model import (
    DesignOptions,
    SequenceValidationError,
    design_polyamide,
    normalize_dna,
)


class ModelTests(unittest.TestCase):
    def test_gtac_hairpin_mapping(self) -> None:
        design = design_polyamide("GTAC")

        self.assertEqual(design.sequence, "GTAC")
        self.assertEqual(design.complement, "CATG")
        self.assertEqual(design.monomer_pairs, ("Im/Py", "Hp/Py", "Py/Hp", "Py/Im"))
        self.assertEqual(
            design.chain_monomers,
            ("Im", "Hp", "Py", "Py", "gamma-turn", "Im", "Hp", "Py", "Py", "Dp"),
        )

    def test_linear_py_py_mode(self) -> None:
        design = design_polyamide(
            "ATGC",
            DesignOptions(architecture="linear", at_mode="py-py", tail="none"),
        )

        self.assertEqual(design.monomer_pairs, ("Py/Py", "Py/Py", "Im/Py", "Py/Im"))
        self.assertEqual(design.chain_code, "Py-Py-Im-Py")
        self.assertTrue(any("Linear mode" in warning for warning in design.warnings))

    def test_fasta_like_input_is_normalized(self) -> None:
        self.assertEqual(normalize_dna(">target\nG T-A_C\n"), "GTAC")

    def test_invalid_input_is_rejected(self) -> None:
        with self.assertRaises(SequenceValidationError):
            normalize_dna("GTX")


if __name__ == "__main__":
    unittest.main()
