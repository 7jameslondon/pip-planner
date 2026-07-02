from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
import gzip
import json
import os
from pathlib import Path
import re
from typing import Iterable, Iterator, TextIO
from urllib.parse import unquote

from .model import COMPLEMENT, normalize_dna


GENOME_NONE_ID = "none"
DEFAULT_LOCATION_THRESHOLD = 100
DEFAULT_FEATURE_LIMIT = 8


@dataclass(frozen=True)
class GenomeReference:
    id: str
    label: str
    fasta: Path | None
    annotations: tuple[Path, ...] = ()
    notes: str = ""

    @property
    def available(self) -> bool:
        return self.fasta is not None and self.fasta.exists()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "available": self.available,
            "fasta": str(self.fasta) if self.fasta is not None else None,
            "annotations": [str(path) for path in self.annotations],
            "notes": self.notes,
        }


@dataclass(frozen=True)
class GenomeFeature:
    contig: str
    source: str
    type: str
    start: int
    end: int
    strand: str
    name: str
    gene_id: str
    biotype: str

    def to_dict(self) -> dict:
        return {
            "contig": self.contig,
            "source": self.source,
            "type": self.type,
            "start": self.start,
            "end": self.end,
            "strand": self.strand,
            "name": self.name,
            "gene_id": self.gene_id,
            "biotype": self.biotype,
        }


@dataclass(frozen=True)
class AnnotationIndex:
    features_by_contig: dict[str, tuple[GenomeFeature, ...]]
    starts_by_contig: dict[str, tuple[int, ...]]

    def overlaps(self, contig: str, start: int, end: int, limit: int = DEFAULT_FEATURE_LIMIT) -> tuple[GenomeFeature, ...]:
        collected: list[GenomeFeature] = []
        seen: set[tuple[str, str, str, int, int, str]] = set()
        for contig_key in _contig_aliases(contig):
            features = self.features_by_contig.get(contig_key)
            starts = self.starts_by_contig.get(contig_key)
            if not features or not starts:
                continue

            stop = bisect_right(starts, end)
            for index in range(stop):
                feature = features[index]
                if feature.end >= start:
                    key = (feature.contig, feature.source, feature.type, feature.start, feature.end, feature.name)
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(feature)
        collected.sort(key=_feature_sort_key)
        return tuple(collected[:limit])


def list_genomes(genome_root: str | Path | None = None) -> list[dict]:
    return [reference.to_dict() for reference in list_genome_references(genome_root)]


def list_genome_references(genome_root: str | Path | None = None) -> tuple[GenomeReference, ...]:
    root = _genome_root(genome_root)
    manifest = root / "genomes.json"
    if manifest.exists():
        try:
            return tuple(_references_from_manifest(root, manifest))
        except (OSError, ValueError, json.JSONDecodeError):
            return tuple(_default_references(root))
    return tuple(_default_references(root))


def analyze_genome_occurrences(
    raw_sequence: str,
    genome_id: str = GENOME_NONE_ID,
    *,
    genome_root: str | Path | None = None,
    location_threshold: int = DEFAULT_LOCATION_THRESHOLD,
    feature_limit: int = DEFAULT_FEATURE_LIMIT,
) -> dict:
    sequence = normalize_dna(raw_sequence)
    references = {reference.id: reference for reference in list_genome_references(genome_root)}

    if genome_id == GENOME_NONE_ID:
        return {
            "status": "skipped",
            "genome_id": GENOME_NONE_ID,
            "genome_label": "Not searched",
            "query": sequence,
            "query_length": len(sequence),
            "total_occurrences": None,
            "searched_strands": [],
            "locations_listed": False,
            "location_threshold": location_threshold,
            "locations": [],
            "message": "Genome occurrence search was not requested.",
        }

    reference = references.get(genome_id)
    if reference is None:
        return {
            "status": "unknown_genome",
            "genome_id": genome_id,
            "genome_label": genome_id,
            "query": sequence,
            "query_length": len(sequence),
            "total_occurrences": None,
            "searched_strands": [],
            "locations_listed": False,
            "location_threshold": location_threshold,
            "locations": [],
            "message": f"Unknown genome '{genome_id}'.",
        }

    if not reference.available:
        return {
            "status": "missing_reference",
            "genome_id": reference.id,
            "genome_label": reference.label,
            "query": sequence,
            "query_length": len(sequence),
            "total_occurrences": None,
            "searched_strands": [],
            "locations_listed": False,
            "location_threshold": location_threshold,
            "locations": [],
            "message": (
                f"Reference FASTA for {reference.label} was not found. "
                "Install the FASTA under the genome data directory or set PIP_PLANNER_GENOME_DIR."
            ),
            "expected_fasta": str(reference.fasta) if reference.fasta is not None else None,
        }

    assert reference.fasta is not None
    reverse_sequence = _reverse_complement(sequence)
    needles = (("+", sequence),) if reverse_sequence == sequence else (("+", sequence), ("-", reverse_sequence))
    stored_hits: list[dict] = []
    total = 0

    for contig, bases in _iter_fasta_records(reference.fasta):
        for strand, needle in needles:
            for offset in _find_all(bases, needle):
                total += 1
                if total <= location_threshold:
                    stored_hits.append(
                        {
                            "contig": contig,
                            "start": offset + 1,
                            "end": offset + len(sequence),
                            "strand": strand,
                        }
                    )

    locations_listed = total < location_threshold
    locations = stored_hits if locations_listed else []
    annotation_note = ""
    existing_annotations = tuple(path for path in reference.annotations if path.exists())
    if locations and existing_annotations:
        annotation_index = _load_annotation_index(tuple(str(path) for path in existing_annotations))
        locations = [_annotate_location(location, annotation_index, feature_limit) for location in locations]
    elif locations:
        annotation_note = "No local annotation files are configured for this genome."
        locations = [
            location
            | {
                "features": [],
                "feature_summary": "No local annotation files are configured for this genome.",
            }
            for location in locations
        ]

    return {
        "status": "ok",
        "genome_id": reference.id,
        "genome_label": reference.label,
        "query": sequence,
        "query_length": len(sequence),
        "total_occurrences": total,
        "searched_strands": [strand for strand, _needle in needles],
        "locations_listed": locations_listed,
        "location_threshold": location_threshold,
        "locations": locations,
        "message": _genome_message(reference.label, total, locations_listed, location_threshold, annotation_note),
    }


def _genome_root(genome_root: str | Path | None = None) -> Path:
    if genome_root is not None:
        return Path(genome_root).expanduser().resolve()
    configured = os.environ.get("PIP_PLANNER_GENOME_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.cwd() / "data" / "genomes").resolve()


def _default_references(root: Path) -> Iterable[GenomeReference]:
    yield GenomeReference(
        id="human-grch38",
        label="Human GRCh38.p14",
        fasta=_resolve_existing_path(root, "human-grch38/genome.fa"),
        annotations=tuple(_resolve_existing_path(root, path) for path in ("human-grch38/annotations.gff3",)),
        notes="GRCh38/hg38 reference genome. Optional annotations can include GENCODE GFF3/GTF and BED tracks.",
    )
    yield GenomeReference(
        id="hela",
        label="HeLa local reference",
        fasta=_resolve_existing_path(root, "hela/genome.fa"),
        annotations=tuple(_resolve_existing_path(root, path) for path in ("hela/annotations.gff3",)),
        notes="User-provided HeLa FASTA or assembly. HeLa controlled-access datasets are not bundled.",
    )


def _references_from_manifest(root: Path, manifest: Path) -> Iterable[GenomeReference]:
    raw_payload = json.loads(manifest.read_text(encoding="utf-8"))
    entries = raw_payload.get("genomes") if isinstance(raw_payload, dict) else raw_payload
    if not isinstance(entries, list):
        raise ValueError("genomes.json must be a list or contain a 'genomes' list.")

    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each genome manifest entry must be an object.")
        genome_id = str(entry["id"])
        label = str(entry.get("label") or genome_id)
        fasta = _resolve_existing_path(root, str(entry["fasta"])) if entry.get("fasta") else None
        raw_annotations = entry.get("annotations", entry.get("annotation", []))
        if isinstance(raw_annotations, str):
            raw_annotations = [raw_annotations]
        if not isinstance(raw_annotations, list):
            raise ValueError("Genome annotations must be a string or list.")
        annotations = tuple(_resolve_existing_path(root, str(path)) for path in raw_annotations)
        yield GenomeReference(
            id=genome_id,
            label=label,
            fasta=fasta,
            annotations=annotations,
            notes=str(entry.get("notes") or ""),
        )


def _resolve_existing_path(root: Path, relative: str) -> Path:
    path = Path(relative).expanduser()
    if not path.is_absolute():
        path = root / path
    if path.exists():
        return path.resolve()

    suffix_candidates = []
    if path.suffix != ".gz":
        suffix_candidates.append(path.with_suffix(path.suffix + ".gz"))
    for suffix in (".fasta", ".fna"):
        if path.suffix.lower() in {".fa", ".fasta", ".fna"}:
            suffix_candidates.append(path.with_suffix(suffix))
            suffix_candidates.append(path.with_suffix(suffix + ".gz"))

    for candidate in suffix_candidates:
        if candidate.exists():
            return candidate.resolve()
    return path.resolve()


def _open_text(path: Path) -> TextIO:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _iter_fasta_records(path: Path) -> Iterator[tuple[str, str]]:
    name: str | None = None
    chunks: list[str] = []
    with _open_text(path) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith(">"):
                if name is not None:
                    yield name, "".join(chunks).upper()
                name = line[1:].split()[0]
                chunks = []
            else:
                chunks.append(line)
    if name is not None:
        yield name, "".join(chunks).upper()


def _find_all(haystack: str, needle: str) -> Iterator[int]:
    offset = haystack.find(needle)
    while offset != -1:
        yield offset
        offset = haystack.find(needle, offset + 1)


def _reverse_complement(sequence: str) -> str:
    return "".join(COMPLEMENT[base] for base in reversed(sequence))


@lru_cache(maxsize=8)
def _load_annotation_index(annotation_paths: tuple[str, ...]) -> AnnotationIndex:
    features_by_contig: dict[str, list[GenomeFeature]] = {}
    for annotation_path in annotation_paths:
        path = Path(annotation_path)
        if not path.exists():
            continue
        for feature in _iter_annotation_features(path):
            features_by_contig.setdefault(feature.contig, []).append(feature)

    sorted_features: dict[str, tuple[GenomeFeature, ...]] = {}
    starts: dict[str, tuple[int, ...]] = {}
    for contig, features in features_by_contig.items():
        ordered = tuple(sorted(features, key=lambda feature: (feature.start, feature.end, feature.type, feature.name)))
        sorted_features[contig] = ordered
        starts[contig] = tuple(feature.start for feature in ordered)

    return AnnotationIndex(features_by_contig=sorted_features, starts_by_contig=starts)


def _iter_annotation_features(path: Path) -> Iterator[GenomeFeature]:
    suffixes = "".join(path.suffixes).lower()
    if ".bed" in suffixes:
        yield from _iter_bed_features(path)
    else:
        yield from _iter_gff_like_features(path)


def _iter_bed_features(path: Path) -> Iterator[GenomeFeature]:
    with _open_text(path) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith(("#", "track ", "browser ")):
                continue
            columns = line.split("\t")
            if len(columns) < 3:
                continue
            try:
                start = int(columns[1]) + 1
                end = int(columns[2])
            except ValueError:
                continue
            name = columns[3] if len(columns) > 3 and columns[3] else "BED feature"
            strand = columns[5] if len(columns) > 5 and columns[5] in {"+", "-", "."} else "."
            yield GenomeFeature(
                contig=columns[0],
                source=path.name,
                type="region",
                start=start,
                end=end,
                strand=strand,
                name=name,
                gene_id="",
                biotype="",
            )


def _iter_gff_like_features(path: Path) -> Iterator[GenomeFeature]:
    with _open_text(path) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            columns = line.split("\t")
            if len(columns) < 9:
                continue
            try:
                start = int(columns[3])
                end = int(columns[4])
            except ValueError:
                continue
            attributes = _parse_attributes(columns[8])
            name = _first_attribute(attributes, "gene_name", "Name", "gene", "standard_name", "product", "ID")
            gene_id = _first_attribute(attributes, "gene_id", "geneID", "gene", "Parent", "ID")
            biotype = _first_attribute(attributes, "gene_biotype", "gene_type", "transcript_biotype", "biotype")
            yield GenomeFeature(
                contig=columns[0],
                source=columns[1] if columns[1] else path.name,
                type=columns[2],
                start=start,
                end=end,
                strand=columns[6],
                name=name,
                gene_id=gene_id,
                biotype=biotype,
            )


def _parse_attributes(raw_attributes: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    if "=" in raw_attributes:
        for part in raw_attributes.split(";"):
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            attributes[key.strip()] = unquote(value.strip().strip('"'))
        return attributes

    for match in re.finditer(r'(\S+)\s+"([^"]*)"', raw_attributes):
        attributes[match.group(1)] = match.group(2)
    return attributes


def _first_attribute(attributes: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = attributes.get(key)
        if value:
            return value
    return ""


def _contig_aliases(contig: str) -> tuple[str, ...]:
    aliases = [contig]
    if contig.startswith("chr"):
        aliases.append(contig[3:])
    else:
        aliases.append(f"chr{contig}")
    if contig in {"MT", "M", "chrM", "chrMT"}:
        aliases.extend(["MT", "M", "chrM", "chrMT"])
    return tuple(dict.fromkeys(aliases))


def _feature_sort_key(feature: GenomeFeature) -> tuple[int, int, int, str]:
    priorities = {
        "gene": 0,
        "enhancer": 0,
        "promoter": 0,
        "regulatory_region": 0,
        "regulatory": 0,
        "transcript": 1,
        "mrna": 1,
        "ncrna": 1,
        "exon": 2,
        "cds": 3,
        "utr": 4,
        "five_prime_utr": 4,
        "three_prime_utr": 4,
        "repeat_region": 5,
        "cpg_island": 5,
        "region": 9,
        "chromosome": 9,
    }
    feature_type = feature.type.lower()
    return (
        priorities.get(feature_type, 6),
        feature.end - feature.start,
        feature.start,
        feature.name,
    )


def _annotate_location(location: dict, annotation_index: AnnotationIndex, feature_limit: int) -> dict:
    features = annotation_index.overlaps(
        str(location["contig"]),
        int(location["start"]),
        int(location["end"]),
        limit=feature_limit,
    )
    feature_dicts = [feature.to_dict() for feature in features]
    return location | {
        "features": feature_dicts,
        "feature_summary": _feature_summary(features),
    }


def _feature_summary(features: tuple[GenomeFeature, ...]) -> str:
    if not features:
        return "No overlap in configured annotation files."
    labels = []
    for feature in features:
        name = feature.name or feature.gene_id or feature.source
        suffix = f" ({feature.biotype})" if feature.biotype else ""
        labels.append(f"{feature.type}: {name}{suffix}")
    return "; ".join(labels)


def _genome_message(
    genome_label: str,
    total: int,
    locations_listed: bool,
    location_threshold: int,
    annotation_note: str,
) -> str:
    if locations_listed:
        detail = f" Locations are listed because there are fewer than {location_threshold} occurrences."
    else:
        detail = f" Locations are not listed because there are {location_threshold} or more occurrences."
    if annotation_note:
        detail = f"{detail} {annotation_note}"
    return f"{genome_label}: found {total} exact occurrence(s) across the configured reference FASTA.{detail}"
