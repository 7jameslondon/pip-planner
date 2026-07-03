from pathlib import Path
import gzip
import hashlib
import tempfile
import unittest
from unittest import mock

from pip_planner.genome import (
    GenomeCatalogEntry,
    analyze_genome_occurrences,
    delete_genome_reference,
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
        self.assertEqual(result["total_possibilities"], 34)
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

    def test_parallel_search_matches_sequential_search(self) -> None:
        with mock.patch.dict("os.environ", {"PIP_PLANNER_GENOME_SEARCH_WORKERS": "1"}):
            sequential = analyze_genome_occurrences("ATGC", "human-grch38", genome_root=FIXTURE_GENOMES)
        with mock.patch.dict("os.environ", {"PIP_PLANNER_GENOME_SEARCH_WORKERS": "2"}):
            parallel = analyze_genome_occurrences("ATGC", "human-grch38", genome_root=FIXTURE_GENOMES)

        for key in ("total_occurrences", "total_possibilities", "locations"):
            self.assertEqual(parallel[key], sequential[key])

    def test_reports_missing_reference_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = analyze_genome_occurrences("ATGC", "human-grch38", genome_root=tmp)

        self.assertEqual(result["status"], "missing_reference")
        self.assertIsNone(result["total_occurrences"])
        self.assertIsNone(result["total_possibilities"])

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

    def test_import_decompresses_gzipped_fasta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "my-reference.fa.gz"
            with gzip.open(source, "wt", encoding="utf-8") as handle:
                handle.write(">chrCustom\nATGCATGC\n")

            result = import_genome_reference(source, label="My Reference", genome_root=tmp)

            self.assertEqual(result["status"], "imported")
            fasta = Path(result["genome"]["fasta"])
            self.assertEqual(fasta.name, "genome.fa")
            self.assertEqual(fasta.read_text(encoding="utf-8"), ">chrCustom\nATGCATGC\n")

    def test_delete_removes_imported_reference_from_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "my-reference.fa"
            source.write_text(">chrCustom\nATGCATGC\n", encoding="utf-8")

            import_genome_reference(source, label="My Reference", genome_root=tmp)
            result = delete_genome_reference("my-reference", genome_root=tmp)

            self.assertEqual(result["status"], "deleted")
            references = {reference.id: reference for reference in list_genome_references(tmp)}
            self.assertNotIn("my-reference", references)
            self.assertFalse((Path(tmp) / "my-reference" / "genome.fa").exists())

    def test_delete_refuses_bundled_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict("os.environ", {"PIP_PLANNER_GENOME_DIR": str(Path(tmp) / "genomes")}):
                with self.assertRaisesRegex(ValueError, "bundled"):
                    delete_genome_reference("sacCer3")

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
                    fasta="tiny/genome.fa",
                    download_url=source.as_uri(),
                    size_label="small",
                    source_url=source.as_uri(),
                    sha256=digest,
                ),
            )

            with mock.patch("pip_planner.genome.CATALOG_REFERENCES", catalog):
                result = download_genome_reference("tiny", genome_root=Path(tmp) / "dest")

            self.assertEqual(result["status"], "downloaded")
            destination = Path(tmp) / "dest" / "tiny" / "genome.fa"
            self.assertTrue(destination.exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), ">chrTiny\nATGCATGC\n")

    def test_download_converts_existing_compressed_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dest"
            compressed = root / "tiny" / "genome.fa.gz"
            compressed.parent.mkdir(parents=True)
            with gzip.open(compressed, "wt", encoding="utf-8") as handle:
                handle.write(">chrTiny\nATGCATGC\n")
            catalog = (
                GenomeCatalogEntry(
                    id="tiny",
                    label="Tiny test genome",
                    fasta="tiny/genome.fa",
                    download_url="https://example.invalid/tiny.fa.gz",
                    size_label="small",
                    source_url="https://example.invalid/",
                ),
            )

            with mock.patch("pip_planner.genome.CATALOG_REFERENCES", catalog):
                with mock.patch("pip_planner.genome.urlopen", side_effect=AssertionError("network should not be used")):
                    result = download_genome_reference("tiny", genome_root=root)

            self.assertEqual(result["status"], "downloaded")
            self.assertEqual((root / "tiny" / "genome.fa").read_text(encoding="utf-8"), ">chrTiny\nATGCATGC\n")
            self.assertFalse(compressed.exists())

    def test_download_promotes_completed_temporary_file_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "dest"
            destination = root / "tiny" / "genome.fa"
            temporary = destination.with_name(destination.name + ".download")
            temporary.parent.mkdir(parents=True)
            with gzip.open(temporary, "wt", encoding="utf-8") as handle:
                handle.write(">chrTiny\nATGCATGC\n")
            payload = temporary.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            catalog = (
                GenomeCatalogEntry(
                    id="tiny",
                    label="Tiny test genome",
                    fasta="tiny/genome.fa",
                    download_url="https://example.invalid/tiny.fa.gz",
                    size_label="small",
                    size_bytes=len(payload),
                    source_url="https://example.invalid/",
                    sha256=digest,
                ),
            )

            with mock.patch("pip_planner.genome.CATALOG_REFERENCES", catalog):
                with mock.patch("pip_planner.genome.urlopen", side_effect=AssertionError("network should not be used")):
                    result = download_genome_reference("tiny", genome_root=root)

            self.assertEqual(result["status"], "downloaded")
            self.assertTrue(destination.exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), ">chrTiny\nATGCATGC\n")
            self.assertFalse(temporary.exists())

    def test_download_resumes_partial_temporary_file(self) -> None:
        class PartialResponse:
            status = 206

            def __init__(self, payload: bytes) -> None:
                self.payload = payload
                self.offset = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback) -> None:
                return None

            def getcode(self) -> int:
                return self.status

            def read(self, size: int = -1) -> bytes:
                if self.offset >= len(self.payload):
                    return b""
                if size < 0:
                    size = len(self.payload) - self.offset
                chunk = self.payload[self.offset : self.offset + size]
                self.offset += len(chunk)
                return chunk

        with tempfile.TemporaryDirectory() as tmp:
            full_payload = gzip.compress(b">chrTiny\nATGCATGC\n")
            split_at = 10
            root = Path(tmp) / "dest"
            destination = root / "tiny" / "genome.fa"
            temporary = destination.with_name(destination.name + ".download")
            temporary.parent.mkdir(parents=True)
            temporary.write_bytes(full_payload[:split_at])
            catalog = (
                GenomeCatalogEntry(
                    id="tiny",
                    label="Tiny test genome",
                    fasta="tiny/genome.fa",
                    download_url="https://example.invalid/tiny.fa.gz",
                    size_label="small",
                    size_bytes=len(full_payload),
                    source_url="https://example.invalid/",
                    sha256=hashlib.sha256(full_payload).hexdigest(),
                ),
            )

            seen_ranges: list[str | None] = []

            def fake_urlopen(request, timeout=0):
                seen_ranges.append(request.get_header("Range"))
                return PartialResponse(full_payload[split_at:])

            with mock.patch("pip_planner.genome.CATALOG_REFERENCES", catalog):
                with mock.patch("pip_planner.genome.urlopen", side_effect=fake_urlopen):
                    result = download_genome_reference("tiny", genome_root=root)

            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(seen_ranges, [f"bytes={split_at}-"])
            self.assertEqual(destination.read_text(encoding="utf-8"), ">chrTiny\nATGCATGC\n")
            self.assertFalse(temporary.exists())


if __name__ == "__main__":
    unittest.main()
