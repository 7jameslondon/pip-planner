from pathlib import Path
import gzip
import hashlib
import tempfile
import unittest
from unittest import mock

from pip_planner.genome import (
    GenomeCatalogEntry,
    analyze_genome_occurrences,
    download_genome_reference,
    import_genome_reference,
    list_genome_references,
)


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

    def test_catalog_lists_public_references_without_hela(self) -> None:
        references = {reference.id: reference for reference in list_genome_references(ROOT / "data" / "genomes")}

        self.assertIn("sacCer3", references)
        self.assertIn("human-grch38", references)
        self.assertNotIn("hela", references)
        self.assertTrue(references["sacCer3"].available)
        self.assertTrue(references["sacCer3"].bundled)

    def test_manifest_can_add_user_references(self) -> None:
        references = {reference.id: reference for reference in list_genome_references(FIXTURE_GENOMES)}

        self.assertIn("human-grch38", references)
        self.assertIn("private-reference", references)
        self.assertTrue(references["human-grch38"].available)
        self.assertTrue(references["private-reference"].available)

    def test_import_adds_custom_reference_to_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "my-reference.fa"
            source.write_text(">chrCustom\nATGCATGC\n", encoding="utf-8")

            result = import_genome_reference(source, label="My Reference", genome_root=tmp)

            self.assertEqual(result["status"], "imported")
            references = {reference.id: reference for reference in list_genome_references(tmp)}
            self.assertIn("my-reference", references)
            self.assertTrue(references["my-reference"].available)

    def test_download_uses_catalog_url_and_checksum(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.fa.gz"
            with gzip.open(source, "wt", encoding="utf-8") as handle:
                handle.write(">chrTiny\nATGCATGC\n")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            catalog = (
                GenomeCatalogEntry(
                    id="tiny",
                    label="Tiny test genome",
                    fasta="tiny/genome.fa.gz",
                    download_url=source.as_uri(),
                    size_label="small",
                    source_url=source.as_uri(),
                    sha256=digest,
                ),
            )

            with mock.patch("pip_planner.genome.CATALOG_REFERENCES", catalog):
                result = download_genome_reference("tiny", genome_root=Path(tmp) / "dest")

            self.assertEqual(result["status"], "downloaded")
            self.assertTrue((Path(tmp) / "dest" / "tiny" / "genome.fa.gz").exists())


if __name__ == "__main__":
    unittest.main()
