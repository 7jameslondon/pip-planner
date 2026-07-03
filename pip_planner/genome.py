from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from functools import lru_cache
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Iterable, Iterator, TextIO
from urllib.parse import unquote
from urllib.request import Request, urlopen

from .model import COMPLEMENT, normalize_dna


GENOME_NONE_ID = "none"
DEFAULT_LOCATION_THRESHOLD = 100
DEFAULT_FEATURE_LIMIT = 8
GENOME_MANIFEST_NAME = "genomes.json"


@dataclass(frozen=True)
class GenomeCatalogEntry:
    id: str
    label: str
    fasta: str
    download_url: str
    size_label: str
    source_url: str
    notes: str = ""
    sha256: str = ""
    size_bytes: int = 0
    bundled: bool = False


CATALOG_REFERENCES: tuple[GenomeCatalogEntry, ...] = (
    GenomeCatalogEntry(
        id="sacCer3",
        label="Saccharomyces cerevisiae sacCer3",
        fasta="sacCer3/genome.fa.gz",
        download_url="https://hgdownload.soe.ucsc.edu/goldenPath/sacCer3/bigZips/sacCer3.fa.gz",
        size_label="3.6 MB",
        size_bytes=3820548,
        source_url="https://hgdownload.soe.ucsc.edu/goldenPath/sacCer3/bigZips/",
        sha256="e3a70396853eff5a012077efbd06cb97d858e12349745d102e316bb8f620f266",
        bundled=True,
        notes="Bundled yeast reference genome for quick checks and testing.",
    ),
    GenomeCatalogEntry(
        id="ce11",
        label="Caenorhabditis elegans ce11",
        fasta="ce11/genome.fa.gz",
        download_url="https://hgdownload.soe.ucsc.edu/goldenPath/ce11/bigZips/ce11.fa.gz",
        size_label="30 MB",
        size_bytes=31816111,
        source_url="https://hgdownload.soe.ucsc.edu/goldenPath/ce11/bigZips/",
        notes="Optional C. elegans model-organism reference.",
    ),
    GenomeCatalogEntry(
        id="dm6",
        label="Drosophila melanogaster dm6",
        fasta="dm6/genome.fa.gz",
        download_url="https://hgdownload.soe.ucsc.edu/goldenPath/dm6/bigZips/dm6.fa.gz",
        size_label="43 MB",
        size_bytes=45153922,
        source_url="https://hgdownload.soe.ucsc.edu/goldenPath/dm6/bigZips/",
        notes="Optional D. melanogaster model-organism reference.",
    ),
    GenomeCatalogEntry(
        id="human-grch38",
        label="Human GRCh38/hg38",
        fasta="human-grch38/genome.fa.gz",
        download_url="https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.fa.gz",
        size_label="938 MB",
        size_bytes=983659424,
        source_url="https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/",
        notes="Large optional human reference. Not bundled with the app.",
    ),
    GenomeCatalogEntry(
        id="mouse-mm39",
        label="Mouse GRCm39/mm39",
        fasta="mouse-mm39/genome.fa.gz",
        download_url="https://hgdownload.soe.ucsc.edu/goldenPath/mm39/bigZips/mm39.fa.gz",
        size_label="830 MB",
        size_bytes=870543764,
        source_url="https://hgdownload.soe.ucsc.edu/goldenPath/mm39/bigZips/",
        notes="Large optional mouse reference. Not bundled with the app.",
    ),
)


@dataclass(frozen=True)
class GenomeReference:
    id: str
    label: str
    fasta: Path | None
    annotations: tuple[Path, ...] = ()
    notes: str = ""
    download_url: str = ""
    sha256: str = ""
    size_label: str = ""
    size_bytes: int = 0
    source_url: str = ""
    source: str = "local"
    bundled: bool = False

    @property
    def available(self) -> bool:
        return self.fasta is not None and self.fasta.exists()

    def to_dict(self) -> dict:
        status = "available" if self.available else "downloadable" if self.download_url else "missing"
        return {
            "id": self.id,
            "label": self.label,
            "available": self.available,
            "status": status,
            "fasta": str(self.fasta) if self.fasta is not None else None,
            "expected_fasta": str(self.fasta) if self.fasta is not None else None,
            "annotations": [str(path) for path in self.annotations],
            "notes": self.notes,
            "download_url": self.download_url,
            "downloadable": bool(self.download_url) and not self.available,
            "sha256": self.sha256,
            "size_label": self.size_label,
            "size_bytes": self.size_bytes,
            "source_url": self.source_url,
            "source": self.source,
            "bundled": self.bundled and self.available,
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
    include_bundled = genome_root is None
    references = {reference.id: reference for reference in _catalog_references(root, include_bundled)}
    manifest = root / GENOME_MANIFEST_NAME
    if manifest.exists():
        try:
            for reference in _references_from_manifest(root, manifest):
                references[reference.id] = reference
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    return tuple(references.values())


def download_genome_reference(
    genome_id: str,
    *,
    genome_root: str | Path | None = None,
    force: bool = False,
) -> dict:
    root = _genome_root(genome_root)
    references = {reference.id: reference for reference in list_genome_references(genome_root)}
    reference = references.get(genome_id)
    if reference is None:
        raise ValueError(f"Unknown genome '{genome_id}'.")
    if reference.available and not force:
        return {
            "status": "already_available",
            "genome": reference.to_dict(),
            "message": f"{reference.label} is already available.",
        }
    if not reference.download_url:
        raise ValueError(f"{reference.label} does not have a configured download URL.")

    entry = _catalog_entry(genome_id)
    relative_fasta = entry.fasta if entry is not None else f"{genome_id}/genome.fa.gz"
    destination = (root / relative_fasta).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".download")

    if not force and _complete_temporary_download(temporary, reference):
        _promote_download(temporary, destination)
        refreshed = {reference.id: reference for reference in list_genome_references(genome_root)}[genome_id]
        return {
            "status": "downloaded",
            "genome": refreshed.to_dict(),
            "message": f"Finished installing {refreshed.label} from a completed download.",
        }

    digest = hashlib.sha256()
    remove_temporary = False
    existing_size = _download_size(temporary)
    request = _download_request(reference.download_url, existing_size, reference.size_bytes)
    with urlopen(request, timeout=60) as response:
        append_download = existing_size > 0 and getattr(response, "status", response.getcode()) == 206
        if append_download:
            _hash_file(temporary, digest)
        else:
            existing_size = 0
        with temporary.open("ab" if append_download else "wb") as target:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                target.write(chunk)

    try:
        if reference.size_bytes and _download_size(temporary) != reference.size_bytes:
            raise RuntimeError(
                f"Downloaded {reference.label} but received {_download_size(temporary):,} bytes; "
                f"expected {reference.size_bytes:,} bytes."
            )
        actual_sha256 = digest.hexdigest()
        if reference.sha256 and actual_sha256.lower() != reference.sha256.lower():
            remove_temporary = True
            raise RuntimeError(
                f"Downloaded {reference.label} but checksum did not match. "
                f"Expected {reference.sha256}, got {actual_sha256}."
            )
        _promote_download(temporary, destination)
    finally:
        if remove_temporary and temporary.exists():
            temporary.unlink()

    refreshed = {reference.id: reference for reference in list_genome_references(genome_root)}[genome_id]
    return {
        "status": "downloaded",
        "genome": refreshed.to_dict(),
        "message": f"Downloaded {refreshed.label}.",
    }


def import_genome_reference(
    source_path: str | Path,
    *,
    genome_id: str | None = None,
    label: str | None = None,
    genome_root: str | Path | None = None,
    overwrite: bool = False,
) -> dict:
    source = Path(source_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise ValueError(f"Genome FASTA was not found: {source}")
    if not _looks_like_fasta(source):
        raise ValueError("Genome file must be .fa, .fasta, .fna, or a gzipped version of one of those formats.")

    root = _genome_root(genome_root)
    label = str(label or _label_from_fasta(source)).strip()
    genome_id = _safe_genome_id(genome_id or label)
    if genome_id == GENOME_NONE_ID:
        raise ValueError("'none' is reserved and cannot be used as a genome id.")

    entry = _catalog_entry(genome_id)
    relative_fasta = entry.fasta if entry is not None else f"{genome_id}/{_imported_fasta_name(source)}"
    destination = (root / relative_fasta).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        raise ValueError(f"Genome '{genome_id}' already has a FASTA at {destination}.")

    if source != destination:
        shutil.copy2(source, destination)

    manifest_entry = {
        "id": genome_id,
        "label": label,
        "fasta": relative_fasta.replace("\\", "/"),
        "notes": "User-imported local reference genome.",
    }
    _upsert_manifest_entry(root, manifest_entry)

    refreshed = {reference.id: reference for reference in list_genome_references(genome_root)}[genome_id]
    return {
        "status": "imported",
        "genome": refreshed.to_dict(),
        "message": f"Imported {refreshed.label}.",
    }


def delete_genome_reference(
    genome_id: str,
    *,
    genome_root: str | Path | None = None,
) -> dict:
    root = _genome_root(genome_root)
    references = {reference.id: reference for reference in list_genome_references(genome_root)}
    reference = references.get(genome_id)
    if reference is None:
        raise ValueError(f"Unknown genome '{genome_id}'.")
    if reference.bundled:
        raise ValueError(f"{reference.label} is bundled with the app and cannot be deleted.")
    if reference.fasta is None:
        raise ValueError(f"{reference.label} does not have a local FASTA path.")

    deleted_paths: list[str] = []
    fasta = reference.fasta.resolve()
    if fasta.exists():
        if not _is_within(fasta, root):
            raise ValueError(f"Refusing to delete a genome file outside the configured genome directory: {fasta}")
        fasta.unlink()
        deleted_paths.append(str(fasta))
        _remove_empty_parents(fasta.parent, root)

    _remove_manifest_entry(root, genome_id)
    return {
        "status": "deleted",
        "genome_id": genome_id,
        "message": f"Deleted {reference.label}.",
        "deleted_paths": deleted_paths,
    }


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
            "total_possibilities": None,
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
            "total_possibilities": None,
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
            "total_possibilities": None,
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
    total_possibilities = 0

    for contig, bases in _iter_fasta_records(reference.fasta):
        total_possibilities += max(0, len(bases) - len(sequence) + 1) * len(needles)
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
        "total_possibilities": total_possibilities,
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
    if getattr(sys, "frozen", False):
        return _user_data_genome_root()
    return (Path.cwd() / "data" / "genomes").resolve()


def _user_data_genome_root() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return (Path(base) / "PIP Planner" / "genomes").resolve()
        return (Path.home() / "AppData" / "Local" / "PIP Planner" / "genomes").resolve()

    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return (Path(base) / "pip-planner" / "genomes").resolve()
    return (Path.home() / ".local" / "share" / "pip-planner" / "genomes").resolve()


def _bundled_genome_root() -> Path | None:
    bases = []
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        bases.append(Path(frozen_base))
    bases.append(Path.cwd())
    bases.append(Path(__file__).resolve().parents[1])

    for base in bases:
        candidate = (base / "data" / "genomes").resolve()
        if candidate.exists():
            return candidate
    return None


def _reference_roots(root: Path, include_bundled: bool) -> tuple[Path, ...]:
    roots = [root]
    bundled = _bundled_genome_root() if include_bundled else None
    if bundled is not None and bundled not in roots:
        roots.append(bundled)
    return tuple(roots)


def _catalog_references(root: Path, include_bundled: bool) -> Iterable[GenomeReference]:
    roots = _reference_roots(root, include_bundled)
    bundled_root = _bundled_genome_root()
    for entry in CATALOG_REFERENCES:
        fasta, source = _resolve_reference_path(roots, root, entry.fasta)
        bundled = entry.bundled and fasta.exists() and bundled_root is not None and _is_within(fasta, bundled_root)
        if bundled:
            source = "bundled"
        yield GenomeReference(
            id=entry.id,
            label=entry.label,
            fasta=fasta,
            annotations=(),
            notes=entry.notes,
            download_url=entry.download_url,
            sha256=entry.sha256,
            size_label=entry.size_label,
            size_bytes=entry.size_bytes,
            source_url=entry.source_url,
            source=source,
            bundled=bundled,
        )


def _catalog_entry(genome_id: str) -> GenomeCatalogEntry | None:
    for entry in CATALOG_REFERENCES:
        if entry.id == genome_id:
            return entry
    return None


def _download_request(url: str, existing_size: int, expected_size: int) -> Request:
    headers = {}
    if existing_size > 0 and expected_size > existing_size:
        headers["Range"] = f"bytes={existing_size}-"
    return Request(url, headers=headers)


def _download_size(path: Path) -> int:
    try:
        return path.stat().st_size if path.exists() else 0
    except OSError:
        return 0


def _complete_temporary_download(path: Path, reference: GenomeReference) -> bool:
    if not path.exists():
        return False
    if not reference.size_bytes and not reference.sha256:
        return False
    if reference.size_bytes and _download_size(path) != reference.size_bytes:
        return False
    if reference.sha256:
        digest = hashlib.sha256()
        _hash_file(path, digest)
        return digest.hexdigest().lower() == reference.sha256.lower()
    return True


def _hash_file(path: Path, digest: "hashlib._Hash") -> None:
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)


def _promote_download(temporary: Path, destination: Path) -> None:
    last_error: OSError | None = None
    for attempt in range(8):
        try:
            temporary.replace(destination)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(min(0.25 * (attempt + 1), 2.0))
    fallback = destination.with_name(destination.name + ".promote")
    for attempt in range(4):
        try:
            shutil.copy2(temporary, fallback)
            if _download_size(fallback) != _download_size(temporary):
                raise OSError(f"Copied download size did not match for {destination}.")
            fallback.replace(destination)
            _unlink_with_retries(temporary)
            return
        except OSError as exc:
            last_error = exc
            if fallback.exists():
                _unlink_with_retries(fallback)
            time.sleep(min(0.5 * (attempt + 1), 2.0))
    assert last_error is not None
    raise last_error


def _unlink_with_retries(path: Path) -> None:
    for attempt in range(4):
        try:
            if path.exists():
                path.unlink()
            return
        except OSError:
            time.sleep(min(0.25 * (attempt + 1), 1.0))


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
            download_url=str(entry.get("download_url") or ""),
            sha256=str(entry.get("sha256") or ""),
            size_label=str(entry.get("size_label") or ""),
            size_bytes=int(entry.get("size_bytes") or 0),
            source_url=str(entry.get("source_url") or ""),
            source="local",
        )


def _resolve_reference_path(roots: tuple[Path, ...], primary_root: Path, relative: str) -> tuple[Path, str]:
    fallback = _resolve_existing_path(primary_root, relative)
    for index, root in enumerate(roots):
        path = _resolve_existing_path(root, relative)
        if path.exists():
            source = "local" if index == 0 else "bundled"
            return path, source
    return fallback, "local"


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


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


def _looks_like_fasta(path: Path) -> bool:
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if not suffixes:
        return False
    if suffixes[-1] == ".gz" and len(suffixes) >= 2:
        return suffixes[-2] in {".fa", ".fasta", ".fna"}
    return suffixes[-1] in {".fa", ".fasta", ".fna"}


def _imported_fasta_name(path: Path) -> str:
    return "genome.fa.gz" if path.suffix.lower() == ".gz" else "genome.fa"


def _label_from_fasta(path: Path) -> str:
    name = path.name
    for suffix in (".fasta.gz", ".fna.gz", ".fa.gz", ".fasta", ".fna", ".fa"):
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return path.stem


def _safe_genome_id(raw_value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", raw_value.strip()).strip("-").lower()
    if not cleaned:
        cleaned = "custom-genome"
    if not cleaned[0].isalnum():
        cleaned = f"genome-{cleaned}"
    return cleaned


def _upsert_manifest_entry(root: Path, entry: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / GENOME_MANIFEST_NAME
    entries: list[dict] = []
    if manifest.exists():
        raw_payload = json.loads(manifest.read_text(encoding="utf-8"))
        raw_entries = raw_payload.get("genomes") if isinstance(raw_payload, dict) else raw_payload
        if isinstance(raw_entries, list):
            entries = [item for item in raw_entries if isinstance(item, dict)]

    updated = False
    for index, existing in enumerate(entries):
        if str(existing.get("id")) == str(entry["id"]):
            entries[index] = entry
            updated = True
            break
    if not updated:
        entries.append(entry)

    manifest.write_text(json.dumps({"genomes": entries}, indent=2) + "\n", encoding="utf-8")


def _remove_manifest_entry(root: Path, genome_id: str) -> None:
    manifest = root / GENOME_MANIFEST_NAME
    if not manifest.exists():
        return
    raw_payload = json.loads(manifest.read_text(encoding="utf-8"))
    raw_entries = raw_payload.get("genomes") if isinstance(raw_payload, dict) else raw_payload
    if not isinstance(raw_entries, list):
        return
    entries = [entry for entry in raw_entries if not (isinstance(entry, dict) and str(entry.get("id")) == genome_id)]
    if len(entries) == len(raw_entries):
        return
    manifest.write_text(json.dumps({"genomes": entries}, indent=2) + "\n", encoding="utf-8")


def _remove_empty_parents(path: Path, root: Path) -> None:
    current = path.resolve()
    root = root.resolve()
    while current != root and _is_within(current, root):
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


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
