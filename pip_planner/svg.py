from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Iterable

from .chemistry import render_rdkit_chemical_svg
from .model import PolyamideDesign, ensure_output_dir
from .molecular_model import write_molecular_model_files
from .solubility import predict_solubility


SVG_STYLE = """
    .bg { fill: #ffffff; }
    .ink { fill: #000000; }
    .muted { fill: #333333; }
    .line { stroke: #000000; stroke-width: 2; fill: none; stroke-linecap: round; stroke-linejoin: round; }
    .polyamide-backbone { stroke: #000000; stroke-width: 5; fill: none; stroke-linecap: round; stroke-linejoin: round; }
    .monomer { stroke: #000000; stroke-width: 4; }
    .im-symbol { fill: #000000; }
    .py-symbol, .hp-symbol, .beta-symbol { fill: #ffffff; }
    .hp-letter { font-family: Georgia, 'Times New Roman', serif; font-size: 22px; font-weight: 700; fill: #000000; dominant-baseline: central; text-anchor: middle; }
    .label { font-family: Arial, Helvetica, sans-serif; font-size: 15px; }
    .small { font-family: Arial, Helvetica, sans-serif; font-size: 12px; }
    .tiny { font-family: Arial, Helvetica, sans-serif; font-size: 10px; }
    .title { font-family: Georgia, 'Times New Roman', serif; font-size: 34px; font-weight: 700; }
    .section-title { font-family: Georgia, 'Times New Roman', serif; font-size: 30px; font-weight: 700; }
    .legend-label { font-family: Georgia, 'Times New Roman', serif; font-size: 26px; font-weight: 700; }
    .turn-symbol { font-family: Georgia, 'Times New Roman', serif; font-size: 26px; font-weight: 700; }
    .base { font-family: Georgia, 'Times New Roman', serif; font-size: 26px; font-weight: 700; }
    .terminus { font-family: Georgia, 'Times New Roman', serif; font-size: 22px; font-weight: 700; }
    .caption { font-family: Arial, Helvetica, sans-serif; font-size: 13px; }
    .mono { font-family: Consolas, 'Liberation Mono', monospace; font-size: 14px; }
"""


def render_schematic_svg(design: PolyamideDesign) -> str:
    count = len(design.base_pairs)
    gap = _schematic_gap(count)
    is_hairpin = design.options.architecture == "hairpin"
    left_bound, right_bound = _schematic_horizontal_bounds(count, gap, is_hairpin, design.options.tail)
    figure_width = right_bound - left_bound
    width = max(840, int(figure_width + 96))
    start_x = (width - figure_width) / 2 - left_bound
    y_top_dna = 84
    y_bottom_dna = 256 if is_hairpin else 232
    figure_bottom = 318 if is_hairpin else 288
    legend_y = figure_bottom + 60
    height = max(430, legend_y + 42)

    parts = [_svg_header(width, height, f"PIP schematic for {design.sequence}")]
    parts.append(f'<rect class="bg" x="0" y="0" width="{width}" height="{height}"/>')
    parts.append('<g class="figure-schematic" data-schematic="polyamide-figure">')
    parts.append(_dna_rows(design, start_x, gap, y_top_dna, y_bottom_dna))

    if is_hairpin:
        parts.append(_hairpin_polyamide_symbols(design, start_x, gap, y_top_dna, y_bottom_dna))
    else:
        parts.append(_linear_polyamide_symbols(design, start_x, gap, y_top_dna, y_bottom_dna))

    parts.append(_schematic_legend((width - 562) / 2, legend_y))
    parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def render_chemical_svg(design: PolyamideDesign) -> str:
    return render_rdkit_chemical_svg(design).svg


def write_design_files(
    design: PolyamideDesign,
    out_dir: str | Path,
    name: str,
    extra_payload: dict | None = None,
) -> dict[str, Path]:
    out_path = ensure_output_dir(out_dir)
    safe_name = _safe_filename(name)
    schematic_path = out_path / f"{safe_name}-schematic.svg"
    chemical_path = out_path / f"{safe_name}-chemical.svg"
    json_path = out_path / f"{safe_name}-design.json"

    schematic_files = write_schematic_file(design, out_path, safe_name)
    schematic_path = schematic_files["schematic_svg"]
    chemical_files, chemical_rendering = write_chemical_file(design, out_path, safe_name)
    chemical_path = chemical_files["chemical_svg"]
    model_payload = write_molecular_model_files(
        design,
        out_path,
        safe_name,
        chemical_rendering.canonical_smiles,
    )
    json_payload = design.to_dict() | {
        "files": {
            "schematic_svg": str(schematic_path),
            "chemical_svg": str(chemical_path),
            "json": str(json_path),
            **model_payload["model_3d"]["files"],
        },
        "chemical_renderer": chemical_rendering.renderer,
        "chemical_smiles": chemical_rendering.canonical_smiles,
        "chemical_svg_note": chemical_rendering.note,
        "solubility_predictions": list(predict_solubility(chemical_rendering.canonical_smiles)),
        **model_payload,
    }
    if extra_payload:
        json_payload |= extra_payload
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    return {
        "schematic_svg": schematic_path,
        "chemical_svg": chemical_path,
        "json": json_path,
    }


def write_schematic_file(design: PolyamideDesign, out_dir: str | Path, name: str) -> dict[str, Path]:
    out_path = ensure_output_dir(out_dir)
    safe_name = _safe_filename(name)
    schematic_path = out_path / f"{safe_name}-schematic.svg"
    schematic_path.write_text(render_schematic_svg(design), encoding="utf-8")
    return {"schematic_svg": schematic_path}


def write_chemical_file(design: PolyamideDesign, out_dir: str | Path, name: str):
    out_path = ensure_output_dir(out_dir)
    safe_name = _safe_filename(name)
    chemical_path = out_path / f"{safe_name}-chemical.svg"
    chemical_rendering = render_rdkit_chemical_svg(design)
    chemical_path.write_text(chemical_rendering.svg, encoding="utf-8")
    return {"chemical_svg": chemical_path}, chemical_rendering


def chemical_rendering_for_design(design: PolyamideDesign):
    return render_rdkit_chemical_svg(design)


def write_model_files(design: PolyamideDesign, out_dir: str | Path, name: str, chemical_smiles: str) -> dict:
    out_path = ensure_output_dir(out_dir)
    safe_name = _safe_filename(name)
    return write_molecular_model_files(design, out_path, safe_name, chemical_smiles)


def _svg_header(width: int, height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">\n'
        f"<title>{escape(title)}</title>\n"
        f"<style>{SVG_STYLE}</style>"
    )


def _text(x: float, y: float, text: str, class_name: str) -> str:
    return f'<text class="{class_name}" x="{x:.1f}" y="{y:.1f}">{escape(str(text))}</text>'


def _text_center(x: float, y: float, text: str, class_name: str) -> str:
    return f'<text class="{class_name}" x="{x:.1f}" y="{y:.1f}" text-anchor="middle">{escape(str(text))}</text>'


def _text_end(x: float, y: float, text: str, class_name: str) -> str:
    return f'<text class="{class_name}" x="{x:.1f}" y="{y:.1f}" text-anchor="end">{escape(str(text))}</text>'


def _box_text(x: float, y: float, width: float, height: float, text: str, class_name: str) -> str:
    box_class = class_name.split()[0]
    text_class = " ".join(class_name.split()[1:] or ["label", "ink"])
    return (
        f'<rect class="{box_class}" x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}"/>'
        f'<text class="{text_class}" x="{x + width / 2:.1f}" y="{y + height / 2 + 5:.1f}" text-anchor="middle">{escape(text)}</text>'
    )


def _schematic_gap(count: int) -> int:
    if count <= 8:
        return 72
    if count <= 14:
        return 62
    return 54


def _schematic_horizontal_bounds(count: int, gap: float, is_hairpin: bool, tail: str) -> tuple[float, float]:
    chain_span = max(0, count - 1) * gap
    left = min(-86.0, -gap * 0.52 - 44)
    if is_hairpin:
        right = max(chain_span + 72, chain_span + gap * 0.50 + 82)
    else:
        right = chain_span + gap * (0.82 if tail == "dp" else 0.58) + 72
    return left, right


def _schematic_legend(x: float, y: float) -> str:
    items = [
        ("Im", "Im", 92, 160),
        ("Py", "Py", 92, 160),
        ("β", "beta", 72, 132),
        ("Hp", "Hp", 92, 0),
    ]
    parts = [
        '<g class="schematic-legend" data-legend="polyamide-symbols">',
    ]
    current_x = x
    for label, monomer, symbol_x, advance in items:
        parts.append(
            f'<g class="legend-item" data-legend-item="{escape(label)}" transform="translate({current_x:.1f},{y:.1f})">'
        )
        parts.append(_text(0, 8, f"{label} =", "legend-label ink"))
        parts.append(_monomer_symbol(monomer, symbol_x, 0, 16))
        parts.append("</g>")
        current_x += advance
    parts.append("</g>")
    return "\n".join(parts)


def _dna_rows(
    design: PolyamideDesign,
    start_x: float,
    gap: float,
    y_top: float,
    y_bottom: float,
) -> str:
    parts = [
        _text(start_x - 66, y_top + 8, "5'", "terminus ink"),
        _text(start_x - 66, y_bottom + 8, "3'", "terminus ink"),
    ]
    x_last = start_x + max(0, len(design.base_pairs) - 1) * gap
    parts.extend(
        [
            _text(x_last + 34, y_top + 8, "3'", "terminus ink"),
            _text(x_last + 34, y_bottom + 8, "5'", "terminus ink"),
        ]
    )

    for index, pair in enumerate(design.base_pairs):
        x = start_x + index * gap
        parts.append(_text_center(x, y_top + 8, pair.target_base, "base ink"))
        parts.append(_text_center(x, y_bottom + 8, pair.complement_base, "base ink"))
    return "\n".join(parts)


def _hairpin_polyamide_symbols(
    design: PolyamideDesign,
    start_x: float,
    gap: float,
    y_top_dna: float,
    y_bottom_dna: float,
) -> str:
    top_y = y_top_dna + 58
    bottom_y = y_bottom_dna - 48
    x_last = start_x + max(0, len(design.base_pairs) - 1) * gap
    left_stub = start_x - gap * 0.52
    turn_x = x_last + gap * 0.50
    turn_label = _turn_symbol(design.options.turn)
    parts = [
        f'<line class="polyamide-backbone" x1="{left_stub:.1f}" y1="{top_y:.1f}" x2="{turn_x:.1f}" y2="{top_y:.1f}"/>',
        f'<path class="polyamide-backbone" d="M {turn_x:.1f},{top_y:.1f} C {turn_x + 34:.1f},{top_y:.1f} {turn_x + 34:.1f},{bottom_y:.1f} {turn_x:.1f},{bottom_y:.1f}"/>',
        f'<line class="polyamide-backbone" x1="{turn_x:.1f}" y1="{bottom_y:.1f}" x2="{left_stub:.1f}" y2="{bottom_y:.1f}"/>',
        _text(turn_x + 48, (top_y + bottom_y) / 2 + 9, turn_label, "turn-symbol ink"),
        _text_center(left_stub - 18, top_y + 8, "+", "section-title ink"),
    ]
    if design.options.tail == "dp":
        parts.append(_text_center(left_stub - 22, bottom_y + 30, "Dp", "small ink"))

    for index, pair in enumerate(design.base_pairs):
        x = start_x + index * gap
        parts.append(_monomer_symbol(pair.top_monomer, x, top_y))
        parts.append(_monomer_symbol(pair.bottom_monomer, x, bottom_y))
    return "\n".join(parts)


def _turn_symbol(turn: str) -> str:
    labels = {
        "gamma": "γ",
        "beta": "β",
        "none": "turn",
    }
    return labels.get(turn, turn)


def _linear_polyamide_symbols(
    design: PolyamideDesign,
    start_x: float,
    gap: float,
    y_top_dna: float,
    y_bottom_dna: float,
) -> str:
    symbol_y = (y_top_dna + y_bottom_dna) / 2 + 10
    x_last = start_x + max(0, len(design.top_monomers) - 1) * gap
    left_stub = start_x - gap * 0.52
    right_stub = x_last + gap * (0.72 if design.options.tail == "dp" else 0.50)
    parts = [
        f'<line class="polyamide-backbone" x1="{left_stub:.1f}" y1="{symbol_y:.1f}" x2="{right_stub:.1f}" y2="{symbol_y:.1f}"/>',
        _text_center(left_stub - 18, symbol_y + 8, "+", "section-title ink"),
    ]
    if design.options.tail == "dp":
        parts.append(_text(right_stub + 10, symbol_y + 5, "Dp", "small ink"))
    for index, monomer in enumerate(design.top_monomers):
        x = start_x + index * gap
        parts.append(_monomer_symbol(monomer, x, symbol_y))
    return "\n".join(parts)


def _monomer_symbol(label: str, x: float, y: float, radius: float = 18) -> str:
    if label == "Im":
        return f'<circle class="monomer im-symbol" cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}"/>'
    if label == "Py":
        return f'<circle class="monomer py-symbol" cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}"/>'
    if label == "Hp":
        return (
            f'<circle class="monomer hp-symbol" cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}"/>'
            f'<text class="hp-letter" x="{x:.1f}" y="{y + 1:.1f}">H</text>'
        )
    if label == "beta" or label.startswith("beta"):
        return f'<polygon class="monomer beta-symbol" points="{_diamond_points(x, y, radius)}"/>'
    return (
        f'<circle class="monomer py-symbol" cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}"/>'
        f'<text class="hp-letter" x="{x:.1f}" y="{y + 1:.1f}">{escape(label[:1])}</text>'
    )


def _diamond_points(x: float, y: float, radius: float) -> str:
    return " ".join(
        f"{point_x:.1f},{point_y:.1f}"
        for point_x, point_y in (
            (x, y - radius),
            (x + radius, y),
            (x, y + radius),
            (x - radius, y),
        )
    )


def _chain_diagram(x: float, y: float, monomers: Iterable[str], max_width: float) -> str:
    parts: list[str] = []
    cursor = x
    row_y = y
    for index, monomer in enumerate(monomers):
        label_width = max(50, 9 * len(monomer) + 22)
        if cursor + label_width > x + max_width and cursor > x:
            cursor = x
            row_y += 44
        if index > 0 and cursor > x:
            parts.append(f'<line class="soft-line" x1="{cursor - 18}" y1="{row_y}" x2="{cursor - 4}" y2="{row_y}"/>')
        parts.append(_box_text(cursor, row_y - 18, label_width, 34, monomer, "pair-box mono"))
        cursor += label_width + 24
    return "\n".join(parts)


def _chain_row_count(monomers: Iterable[str], max_width: float) -> int:
    cursor = 0.0
    rows = 1
    for monomer in monomers:
        label_width = max(50, 9 * len(monomer) + 22)
        advance = label_width + 24
        if cursor and cursor + label_width > max_width:
            rows += 1
            cursor = 0
        cursor += advance
    return rows


def _wrap_plain_text(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _safe_filename(name: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe or "pip-design"
