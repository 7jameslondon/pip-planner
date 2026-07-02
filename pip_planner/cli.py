from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .genome import GENOME_NONE_ID, analyze_genome_occurrences
from .model import DesignOptions, SequenceValidationError, design_polyamide, safe_design_name
from .svg import write_design_files


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
        help="Local genome reference to scan for exact occurrences. Use 'human-grch38', 'hela', or 'none'. Default: none.",
    )
    design_parser.add_argument(
        "--genome-location-threshold",
        type=int,
        default=100,
        help="List occurrence locations only when the total count is below this value. Default: 100.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] not in {"design", "-h", "--help"}:
        argv = ["design", *argv]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

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
    except SequenceValidationError as exc:
        parser.error(str(exc))
    except RuntimeError as exc:
        print(f"pip-planner: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"pip-planner: could not write output files: {exc}", file=sys.stderr)
        return 2

    payload = persisted_payload

    if args.format == "json":
        print(json.dumps(payload, indent=2))
    else:
        print(_format_text_summary(payload))

    return 0


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
