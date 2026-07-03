from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .genome import (
    GENOME_NONE_ID,
    analyze_genome_occurrences,
    delete_genome_reference,
    download_genome_reference,
    import_genome_reference,
    list_genomes,
)
from .model import DesignOptions, SequenceValidationError, design_polyamide, safe_design_name
from .solubility import predict_solubility
from .svg import (
    chemical_rendering_for_design,
    write_chemical_file,
    write_design_files,
    write_model_files,
    write_schematic_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pip-planner",
        description="Design pyrrole-imidazole polyamide candidates from DNA sequences.",
    )
    subparsers = parser.add_subparsers(dest="command")

    design_parser = subparsers.add_parser(
        "design",
        help="Generate a PIP design and SVG files from a DNA sequence.",
    )
    design_parser.add_argument("sequence", help="DNA sequence, read as the 5' to 3' target strand.")
    design_parser.add_argument(
        "--architecture",
        choices=["hairpin", "linear"],
        default="hairpin",
        help="Polyamide architecture to render. Default: hairpin.",
    )
    design_parser.add_argument(
        "--at-mode",
        choices=["distinguish", "py-py"],
        default="distinguish",
        help="Use Hp to distinguish A-T/T-A or use Py/Py as A/T-degenerate. Default: distinguish.",
    )
    design_parser.add_argument(
        "--tail",
        choices=["dp", "none"],
        default="dp",
        help="Terminal group to include in the planning structure. Default: dp.",
    )
    design_parser.add_argument(
        "--turn",
        choices=["gamma", "beta", "none"],
        default="gamma",
        help="Hairpin turn label. Ignored by linear mode. Default: gamma.",
    )
    design_parser.add_argument(
        "--out",
        default="output/designs",
        help="Directory for schematic SVG, chemical SVG, and JSON output.",
    )
    design_parser.add_argument(
        "--name",
        default=None,
        help="Base filename for generated files. Default uses the sequence and architecture.",
    )
    design_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Write a human summary or machine-readable JSON to stdout. Default: text.",
    )
    design_parser.add_argument(
        "--genome",
        default=GENOME_NONE_ID,
        help="Genome reference id to scan for exact occurrences. Use 'pip-planner genomes list' to see available ids. Default: none.",
    )
    design_parser.add_argument(
        "--genome-location-threshold",
        type=int,
        default=100,
        help="List occurrence locations only when the total count is below this value. Default: 100.",
    )
    design_parser.add_argument(
        "--product",
        choices=["all", "schematic", "chemical", "solubility", "genome", "model"],
        default="all",
        help="Generate one product for incremental UI updates, or all products. Default: all.",
    )

    genomes_parser = subparsers.add_parser(
        "genomes",
        help="List, download, or import local genome references.",
    )
    genomes_subparsers = genomes_parser.add_subparsers(dest="genomes_command")

    genomes_list = genomes_subparsers.add_parser("list", help="List configured genome references.")
    genomes_list.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Write a human summary or machine-readable JSON. Default: text.",
    )

    genomes_download = genomes_subparsers.add_parser("download", help="Download a curated genome reference.")
    genomes_download.add_argument("genome", help="Genome id to download.")
    genomes_download.add_argument(
        "--force",
        action="store_true",
        help="Download again even when a local or bundled FASTA is already available.",
    )
    genomes_download.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Write a human summary or machine-readable JSON. Default: text.",
    )

    genomes_import = genomes_subparsers.add_parser("import", help="Import a user-provided FASTA file.")
    genomes_import.add_argument("fasta", help="Path to a .fa, .fasta, .fna, or gzipped FASTA file.")
    genomes_import.add_argument("--id", dest="genome_id", default=None, help="Genome id to add to the list.")
    genomes_import.add_argument("--label", default=None, help="Human-readable genome label.")
    genomes_import.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing FASTA for the same genome id.",
    )
    genomes_import.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Write a human summary or machine-readable JSON. Default: text.",
    )

    genomes_delete = genomes_subparsers.add_parser("delete", help="Delete a downloaded or imported genome reference.")
    genomes_delete.add_argument("genome", help="Genome id to delete.")
    genomes_delete.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Write a human summary or machine-readable JSON. Default: text.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] not in {"design", "genomes", "-h", "--help"}:
        argv = ["design", *argv]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "genomes":
        return _handle_genomes_command(args, parser)

    if args.command != "design":
        parser.error("Unsupported command.")
    if args.genome_location_threshold < 1:
        parser.error("--genome-location-threshold must be at least 1.")

    try:
        options = DesignOptions(
            architecture=args.architecture,
            at_mode=args.at_mode,
            tail=args.tail,
            turn=args.turn,
        )
        design = design_polyamide(args.sequence, options)
        name = args.name or safe_design_name(design.sequence, design.options.architecture)
        if args.product == "all":
            genome_occurrences = analyze_genome_occurrences(
                design.sequence,
                args.genome,
                location_threshold=args.genome_location_threshold,
            )
            if genome_occurrences["status"] == "unknown_genome":
                parser.error(str(genome_occurrences["message"]))
            files = write_design_files(
                design,
                Path(args.out),
                name,
                extra_payload={"genome_occurrences": genome_occurrences},
            )
            persisted_payload = json.loads(files["json"].read_text(encoding="utf-8"))
        else:
            persisted_payload = _generate_product_payload(design, args, Path(args.out), name)
    except SequenceValidationError as exc:
        parser.error(str(exc))
    except RuntimeError as exc:
        print(f"pip-planner: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"pip-planner: could not write output files: {exc}", file=sys.stderr)
        return 2

    payload = persisted_payload

    if args.format == "json" or args.product != "all":
        print(json.dumps(payload, indent=2))
    else:
        print(_format_text_summary(payload))

    return 0


def _handle_genomes_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.genomes_command is None:
        parser.error("genomes requires one of: list, download, import, delete.")

    try:
        if args.genomes_command == "list":
            payload = {"genomes": list_genomes()}
        elif args.genomes_command == "download":
            payload = download_genome_reference(args.genome, force=args.force)
        elif args.genomes_command == "import":
            payload = import_genome_reference(
                args.fasta,
                genome_id=args.genome_id,
                label=args.label,
                overwrite=args.overwrite,
            )
        elif args.genomes_command == "delete":
            payload = delete_genome_reference(args.genome)
        else:
            parser.error("Unsupported genomes command.")
    except (ValueError, RuntimeError, OSError) as exc:
        parser.error(str(exc))

    if args.format == "json":
        print(json.dumps(payload, indent=2))
    elif args.genomes_command == "list":
        print(_format_genome_catalog_rows(payload["genomes"]))
    else:
        print(payload.get("message") or payload.get("status") or "Done.")
    return 0


def _generate_product_payload(design, args: argparse.Namespace, out_dir: Path, name: str) -> dict:
    payload = design.to_dict() | {"product": args.product, "files": {}}

    if args.product == "schematic":
        files = write_schematic_file(design, out_dir, name)
        return payload | {"files": _string_paths(files)}

    if args.product == "chemical":
        files, rendering = write_chemical_file(design, out_dir, name)
        return payload | {
            "files": _string_paths(files),
            "chemical_renderer": rendering.renderer,
            "chemical_smiles": rendering.canonical_smiles,
            "chemical_svg_note": rendering.note,
        }

    if args.product == "solubility":
        rendering = chemical_rendering_for_design(design)
        return payload | {
            "chemical_renderer": rendering.renderer,
            "chemical_smiles": rendering.canonical_smiles,
            "solubility_predictions": list(predict_solubility(rendering.canonical_smiles)),
        }

    if args.product == "genome":
        genome_occurrences = analyze_genome_occurrences(
            design.sequence,
            args.genome,
            location_threshold=args.genome_location_threshold,
        )
        if genome_occurrences["status"] == "unknown_genome":
            raise SequenceValidationError(str(genome_occurrences["message"]))
        return payload | {"genome_occurrences": genome_occurrences}

    if args.product == "model":
        rendering = chemical_rendering_for_design(design)
        model_payload = write_model_files(design, out_dir, name, rendering.canonical_smiles)
        return payload | {
            "files": _string_paths(model_payload["model_3d"]["files"]),
            "chemical_renderer": rendering.renderer,
            "chemical_smiles": rendering.canonical_smiles,
            **model_payload,
        }

    raise RuntimeError(f"Unsupported product: {args.product}")


def _string_paths(paths: dict[str, Path | str]) -> dict[str, str]:
    return {key: str(value) for key, value in paths.items()}


def _format_text_summary(payload: dict) -> str:
    rows = [
        "PIP Planner design",
        f"Target:       {payload['sequence_label']}",
        f"Complement:   {payload['complement_label']}",
        f"Architecture: {payload['architecture']}",
        f"A/T mode:     {payload['at_mode']}",
        f"Pairs:        {' '.join(payload['recognition_pairs'])}",
        f"Chain:        {payload['chain_code']}",
        "",
        "Base-pair map:",
    ]

    for pair in payload["base_pairs"]:
        rows.append(
            f"  {pair['position']:>2}. {pair['base_pair']:<3} -> {pair['monomer_pair']:<5} "
            f"({pair['target_base']}/{pair['complement_base']})"
        )

    rows.extend(
        [
            "",
            "Solubility predictions:",
            *_format_solubility_rows(payload.get("solubility_predictions", [])),
            "",
            "Genome occurrences:",
            *_format_genome_rows(payload.get("genome_occurrences", {})),
            "",
            "3D/MD model:",
            *_format_model_rows(payload.get("model_3d", {})),
            "",
            f"Schematic SVG: {payload['files']['schematic_svg']}",
            f"Chemical SVG:  {payload['files']['chemical_svg']}",
            f"Complex PDB:   {payload['files']['complex_pdb']}",
            f"Design JSON:   {payload['files']['json']}",
        ]
    )

    if payload["warnings"]:
        rows.append("")
        rows.append("Warnings:")
        for warning in payload["warnings"]:
            rows.append(f"  - {warning}")

    return "\n".join(rows)


def _format_solubility_rows(predictions: list[dict]) -> list[str]:
    if not predictions:
        return ["  - No solubility predictors were run."]

    rows = []
    for prediction in predictions:
        method = str(prediction.get("method") or "Unknown predictor")
        status = str(prediction.get("status") or "unknown")
        if status == "ok":
            value = prediction.get("value")
            unit = prediction.get("unit") or "predicted logS"
            property_name = prediction.get("property_name")
            detail = f" ({property_name})" if property_name else ""
            rows.append(f"  - {method}: {float(value):.3g} {unit}{detail}")
        else:
            message = prediction.get("message") or status
            rows.append(f"  - {method}: {status} - {message}")
    return rows


def _format_genome_rows(genome_result: dict) -> list[str]:
    status = genome_result.get("status") or "skipped"
    if status == "skipped":
        return ["  - Not searched."]
    if status == "missing_reference":
        return [f"  - {genome_result.get('genome_label', 'Genome')}: missing local FASTA."]
    if status != "ok":
        message = genome_result.get("message") or status
        return [f"  - {message}"]

    genome_label = genome_result.get("genome_label") or genome_result.get("genome_id") or "Genome"
    total = genome_result.get("total_occurrences")
    rows = [f"  - {genome_label}: {total} exact occurrence(s)."]
    if genome_result.get("locations_listed"):
        for location in genome_result.get("locations", []):
            rows.append(
                "    "
                f"{location['contig']}:{location['start']}-{location['end']} "
                f"({location['strand']}) - {location.get('feature_summary', 'No annotation')}"
            )
    return rows


def _format_genome_catalog_rows(genomes: list[dict]) -> str:
    rows = ["Genome references:"]
    for genome in genomes:
        label = genome.get("label") or genome.get("id") or "Genome"
        status = genome.get("status") or "missing"
        detail = "available" if genome.get("available") else status
        size = f" ({genome['size_label']})" if genome.get("size_label") else ""
        rows.append(f"  - {genome.get('id')}: {label}{size} - {detail}")
    return "\n".join(rows)


def _format_model_rows(model_result: dict) -> list[str]:
    if not model_result:
        return ["  - Not generated."]
    simulation = model_result.get("md_simulation") or {}
    status = simulation.get("status") or model_result.get("status") or "unknown"
    message = simulation.get("message") or model_result.get("model_type") or ""
    return [
        f"  - Model: {model_result.get('model_type', '3D complex model')}",
        f"  - MD status: {status} - {message}",
    ]
