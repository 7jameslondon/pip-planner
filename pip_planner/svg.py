from __future__ import annotations

from html import escape
import json
from pathlib import Path
from typing import Iterable

from .chemistry import render_rdkit_chemical_svg
from .model import PolyamideDesign, ensure_output_dir


SVG_STYLE = """
    .bg { fill: #f8fafc; }
    .ink { fill: #172033; }
    .muted { fill: #5f6b7a; }
    .line { stroke: #344054; stroke-width: 2; fill: none; stroke-linecap: round; stroke-linejoin: round; }
    .soft-line { stroke: #98a2b3; stroke-width: 1.4; fill: none; stroke-linecap: round; stroke-linejoin: round; }
    .amide { stroke: #406b5a; stroke-width: 2; fill: none; stroke-linecap: round; stroke-linejoin: round; }
    .pair-box { fill: #ffffff; stroke: #cbd5e1; stroke-width: 1.2; rx: 6; }
    .top-box { fill: #eff6ff; stroke: #9fc0ea; stroke-width: 1.2; rx: 6; }
    .bottom-box { fill: #f6f1e7; stroke: #d9c6a5; stroke-width: 1.2; rx: 6; }
    .ring { fill: #ffffff; stroke: #172033; stroke-width: 2; }
    .ring-soft { fill: #fefdf9; stroke: #172033; stroke-width: 1.6; }
    .atom { fill: #0f5d4f; font-weight: 700; }
    .oxygen { fill: #9c2f2f; font-weight: 700; }
    .label { font-family: Arial, Helvetica, sans-serif; font-size: 15px; }
    .small { font-family: Arial, Helvetica, sans-serif; font-size: 12px; }
    .tiny { font-family: Arial, Helvetica, sans-serif; font-size: 10px; }
    .title { font-family: Arial, Helvetica, sans-serif; font-size: 22px; font-weight: 700; }
    .mono { font-family: Consolas, 'Liberation Mono', monospace; font-size: 14px; }
"""


def render_schematic_svg(design: PolyamideDesign) -> str:
    count = len(design.base_pairs)
    width = max(780, 110 * count + 180)
    chain_y = 320
    chain_rows = _chain_row_count(design.chain_monomers, width - 68)
    warning_text = " | ".join(design.warnings)
    warning_lines = _wrap_plain_text(warning_text, max(76, int((width - 68) / 7))) if warning_text else []
    warning_y = chain_y + 44 * (chain_rows - 1) + 54
    height = max(410, warning_y + 18 * len(warning_lines) + 26)
    start_x = 92
    gap = 110

    parts = [_svg_header(width, height, f"PIP schematic for {design.sequence}")]
    parts.append(f'<rect class="bg" x="0" y="0" width="{width}" height="{height}"/>')
    parts.append(
        _text(34, 42, f"PIP schematic: 5'-{design.sequence}-3'", "title ink")
    )
    parts.append(
        _text(
            34,
            69,
            f"Architecture: {design.options.architecture} | A/T mode: {design.options.at_mode} | Chain: {design.chain_code}",
            "label muted",
        )
    )

    y_dna_top = 118
    y_dna_bottom = 248
    y_pair = 172
    y_top_monomer = 148
    y_bottom_monomer = 218

    parts.append(_text(34, y_dna_top + 5, "5'", "label muted"))
    parts.append(_text(34, y_dna_bottom + 5, "3'", "label muted"))
    parts.append(_text(width - 42, y_dna_top + 5, "3'", "label muted"))
    parts.append(_text(width - 42, y_dna_bottom + 5, "5'", "label muted"))

    if count > 1:
        x_first = start_x
        x_last = start_x + (count - 1) * gap
        parts.append(f'<line class="soft-line" x1="{x_first}" y1="{y_dna_top}" x2="{x_last}" y2="{y_dna_top}"/>')
        parts.append(f'<line class="soft-line" x1="{x_first}" y1="{y_dna_bottom}" x2="{x_last}" y2="{y_dna_bottom}"/>')

    for index, pair in enumerate(design.base_pairs):
        x = start_x + index * gap
        parts.append(_text_center(x, y_dna_top + 5, pair.target_base, "label ink"))
        parts.append(_text_center(x, y_dna_bottom + 5, pair.complement_base, "label ink"))
        parts.append(f'<line class="soft-line" x1="{x}" y1="{y_dna_top + 14}" x2="{x}" y2="{y_dna_bottom - 14}"/>')
        parts.append(_box_text(x - 32, y_top_monomer - 22, 64, 32, pair.top_monomer, "top-box"))
        parts.append(_box_text(x - 36, y_pair - 18, 72, 32, pair.monomer_pair, "pair-box mono"))
        parts.append(_box_text(x - 32, y_bottom_monomer - 10, 64, 32, pair.bottom_monomer, "bottom-box"))
        parts.append(_text_center(x, y_pair + 46, pair.base_pair, "small muted"))

    parts.append(_text(34, chain_y - 24, "Polyamide chain", "label ink"))
    parts.append(_chain_diagram(34, chain_y, design.chain_monomers, width - 68))

    for index, line in enumerate(warning_lines):
        parts.append(_text(34, warning_y + index * 18, line, "small muted"))

    parts.append("</svg>")
    return "\n".join(parts)


def render_chemical_svg(design: PolyamideDesign) -> str:
    return render_rdkit_chemical_svg(design).svg


def write_design_files(design: PolyamideDesign, out_dir: str | Path, name: str) -> dict[str, Path]:
    out_path = ensure_output_dir(out_dir)
    safe_name = _safe_filename(name)
    schematic_path = out_path / f"{safe_name}-schematic.svg"
    chemical_path = out_path / f"{safe_name}-chemical.svg"
    json_path = out_path / f"{safe_name}-design.json"

    schematic_path.write_text(render_schematic_svg(design), encoding="utf-8")
    chemical_rendering = render_rdkit_chemical_svg(design)
    chemical_path.write_text(chemical_rendering.svg, encoding="utf-8")
    json_payload = design.to_dict() | {
        "files": {
            "schematic_svg": str(schematic_path),
            "chemical_svg": str(chemical_path),
            "json": str(json_path),
        },
        "chemical_renderer": chemical_rendering.renderer,
        "chemical_smiles": chemical_rendering.canonical_smiles,
        "chemical_svg_note": chemical_rendering.note,
    }
    json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

    return {
        "schematic_svg": schematic_path,
        "chemical_svg": chemical_path,
        "json": json_path,
    }


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


def _box_text(x: float, y: float, width: float, height: float, text: str, class_name: str) -> str:
    box_class = class_name.split()[0]
    text_class = " ".join(class_name.split()[1:] or ["label", "ink"])
    return (
        f'<rect class="{box_class}" x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}"/>'
        f'<text class="{text_class}" x="{x + width / 2:.1f}" y="{y + height / 2 + 5:.1f}" text-anchor="middle">{escape(text)}</text>'
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
