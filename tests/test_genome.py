from pathlib import Path
import tempfile
import unittest

from pip_planner.genome import analyze_genome_occurrences, list_genome_references


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_GENOMES = ROOT / "tests" / "fixtures" / "genomes"


class GenomeOccurrenceTests(unittest.TestCase):
    def test_counts_both_strands_and_annotates_locations(self) -> None:
        result = analyze_genome_occurrences(
            "ATGC",
            "human-grch38",
            genome_root=FIXTURE_GENOMES,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_occurrences"], 2)
        self.assertTrue(result["locations_listed"])
        self.assertEqual(
            [(hit["contig"], hit["start"], hit["end"], hit["strand"]) for hit in result["locations"]],
            [("chr1", 4, 7, "+"), ("chr1", 10, 13, "-")],
        )
        self.assertIn("GENE1", result["locations"][0]["feature_summary"])
        self.assertIn("ENH1", result["locations"][1]["feature_summary"])

    def test_hides_locations_at_threshold(self) -> None:
        result = analyze_genome_occurrences(
            "ATGC",
            "human-grch38",
            genome_root=FIXTURE_GENOMES,
            location_threshold=2,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_occurrences"], 2)
        self.assertFalse(result["locations_listed"])
        self.assertEqual(result["locations"], [])

    def test_reports_missing_reference_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_genome_occurrences("ATGC", "human-grch38", genome_root=tmp)

        self.assertEqual(result["status"], "missing_reference")
        self.assertIsNone(result["total_occurrences"])

    def test_manifest_lists_human_and_hela_references(self) -> None:
        references = {reference.id: reference for reference in list_genome_references(FIXTURE_GENOMES)}

        self.assertEqual(set(references), {"human-grch38", "hela"})
        self.assertTrue(references["human-grch38"].available)
        self.assertTrue(references["hela"].available)


if __name__ == "__main__":
    unittest.main()
