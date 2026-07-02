from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil

from .chemistry import build_rdkit_polyamide_mol
from .model import COMPLEMENT, PolyamideDesign


DNA_FORCE_FIELD = "AMBER DNA.OL24"
BINDER_FORCE_FIELD = "GAFF2"
WATER_MODEL = "OPC or a matched TIP4P-Ew/TIP3P water/ion set"
DEFAULT_FLANK = "CGCG"

RISE = 3.4
TWIST_DEGREES = 36.0


@dataclass(frozen=True)
class ModelAtom:
    serial: int
    name: str
    element: str
    residue: str
    chain: str
    residue_number: int
    x: float
    y: float
    z: float
    group: str

    def to_dict(self) -> dict:
        return {
            "id": self.serial,
            "name": self.name,
            "element": self.element,
            "residue": self.residue,
            "chain": self.chain,
            "residue_number": self.residue_number,
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "z": round(self.z, 4),
            "group": self.group,
        }


@dataclass(frozen=True)
class ModelBond:
    a: int
    b: int
    group: str

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "group": self.group}


@dataclass(frozen=True)
class MolecularModel:
    atoms: tuple[ModelAtom, ...]
    bonds: tuple[ModelBond, ...]
    metadata: dict

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata,
            "atoms": [atom.to_dict() for atom in self.atoms],
            "bonds": [bond.to_dict() for bond in self.bonds],
        }


def write_molecular_model_files(
    design: PolyamideDesign,
    out_dir: Path,
    safe_name: str,
    chemical_smiles: str,
) -> dict:
    model = build_molecular_model(design, chemical_smiles)
    model_json = model.to_dict()

    pdb_path = out_dir / f"{safe_name}-complex-model.pdb"
    json_path = out_dir / f"{safe_name}-complex-model.json"
    html_path = out_dir / f"{safe_name}-complex-viewer.html"
    protocol_path = out_dir / f"{safe_name}-md-protocol.md"

    pdb_path.write_text(render_pdb(model), encoding="utf-8")
    json_path.write_text(json.dumps(model_json, indent=2), encoding="utf-8")
    html_path.write_text(render_model_viewer_html(model_json), encoding="utf-8")
    protocol_path.write_text(render_md_protocol(design, chemical_smiles, model.metadata), encoding="utf-8")

    simulation = model.metadata["md_simulation"]
    return {
        "model_3d": {
            "status": model.metadata["status"],
            "model_type": model.metadata["model_type"],
            "atom_count": len(model.atoms),
            "bond_count": len(model.bonds),
            "dna_force_field": DNA_FORCE_FIELD,
            "binder_force_field": BINDER_FORCE_FIELD,
            "water_model": WATER_MODEL,
            "md_simulation": simulation,
            "files": {
                "complex_pdb": str(pdb_path),
                "model_json": str(json_path),
                "model_html": str(html_path),
                "md_protocol": str(protocol_path),
            },
        }
    }


def build_molecular_model(design: PolyamideDesign, chemical_smiles: str) -> MolecularModel:
    atoms: list[ModelAtom] = []
    bonds: list[ModelBond] = []
    modeled_sequence = f"{DEFAULT_FLANK}{design.sequence}{DEFAULT_FLANK}"
    modeled_complement = "".join(COMPLEMENT[base] for base in modeled_sequence)
    target_start = len(DEFAULT_FLANK) + 1
    target_end = len(DEFAULT_FLANK) + len(design.sequence)

    _add_dna_duplex(atoms, bonds, modeled_sequence, modeled_complement)
    _add_polyamide_ligand(atoms, bonds, design, target_start_index=len(DEFAULT_FLANK))

    metadata = {
        "status": "initial_model",
        "model_type": "B-DNA initial minor-groove pose with RDKit polyamide conformer",
        "sequence": design.sequence,
        "complement": design.complement,
        "modeled_sequence": modeled_sequence,
        "modeled_complement": modeled_complement,
        "target_site_residues": f"{target_start}-{target_end}",
        "flanking_bases_each_side": len(DEFAULT_FLANK),
        "chemical_smiles": chemical_smiles,
        "dna_force_field": DNA_FORCE_FIELD,
        "binder_force_field": BINDER_FORCE_FIELD,
        "water_model": WATER_MODEL,
        "md_simulation": _md_engine_status(),
        "notes": [
            "The displayed structure is an initial modeled pose, not a validated production MD trajectory.",
            "Ligand GAFF2 atom types, protonation, total charge, and torsions need validation before production MD.",
        ],
    }
    return MolecularModel(atoms=tuple(atoms), bonds=tuple(bonds), metadata=metadata)


def render_pdb(model: MolecularModel) -> str:
    lines = [
        "HEADER    PIP PLANNER DNA POLYAMIDE INITIAL MODEL",
        f"REMARK 100 MODEL TYPE: {model.metadata['model_type']}",
        f"REMARK 100 DNA FORCE FIELD TARGET: {DNA_FORCE_FIELD}",
        f"REMARK 100 BINDER FORCE FIELD TARGET: {BINDER_FORCE_FIELD}",
        f"REMARK 100 MD STATUS: {model.metadata['md_simulation']['status']}",
    ]
    for atom in model.atoms:
        record = "HETATM" if atom.group == "ligand" else "ATOM  "
        atom_name = atom.name[:4]
        residue = atom.residue[:3]
        lines.append(
            f"{record}{atom.serial:5d} {atom_name:<4} {residue:>3} {atom.chain:1}"
            f"{atom.residue_number:4d}    {atom.x:8.3f}{atom.y:8.3f}{atom.z:8.3f}"
            f"  1.00  0.00          {atom.element:>2}"
        )
    for bond in model.bonds:
        lines.append(f"CONECT{bond.a:5d}{bond.b:5d}")
    lines.append("END")
    return "\n".join(lines) + "\n"


def render_md_protocol(design: PolyamideDesign, chemical_smiles: str, metadata: dict) -> str:
    simulation = metadata["md_simulation"]
    return "\n".join(
        [
            "# PIP Planner MD Protocol Notes",
            "",
            f"Target sequence: `{design.sequence}`",
            f"Polyamide chain: `{design.chain_code}`",
            f"RDKit SMILES: `{chemical_smiles}`",
            "",
            "## Recommended Force Field Setup",
            "",
            f"- DNA: {DNA_FORCE_FIELD}.",
            "- Binder: GAFF2 with checked atom types, protonation/tautomer state, total charge, and torsions.",
            "- Charges: RESP-style QM charges or a validated AmberTools GAFF2 charge workflow for production work.",
            f"- Water/ions: {WATER_MODEL}. Do not mix water and ion parameter sets casually.",
            "- Engine: Amber pmemd.cuda preferred; OpenMM or GROMACS are acceptable only with careful AMBER topology conversion.",
            "",
            "## Practical Production Workflow",
            "",
            "1. Build a duplex containing the target site plus several flanking base pairs.",
            "2. Place or dock the polyamide in the minor groove using Py/Im recognition geometry.",
            "3. Generate ligand parameters with AmberTools GAFF2 and reviewed charges.",
            "4. Solvate with more than 10 Angstrom padding, neutralize, and add the desired salt.",
            "5. Minimize and equilibrate with staged restraints, then release restraints gradually.",
            "6. Run multiple independent replicas. Use hundreds of ns to microsecond-scale sampling for pose stability or selectivity claims.",
            "7. Analyze DNA helical parameters, minor-groove width, binder RMSD, H-bonds, water bridges, ion contacts, and end fraying.",
            "",
            "## Local Execution Status",
            "",
            f"- Status: {simulation['status']}",
            f"- Message: {simulation['message']}",
        ]
    ) + "\n"


def render_model_viewer_html(model_json: dict) -> str:
    model_payload = json.dumps(model_json, separators=(",", ":"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PIP Planner 3D Model</title>
  <style>
    html, body {{ margin: 0; height: 100%; overflow: hidden; background: #000; }}
    canvas {{ display: block; width: 100vw; height: 100vh; background: #000; }}
  </style>
</head>
<body>
<canvas id="scene"></canvas>
<script>
const MODEL = {model_payload};
const canvas = document.getElementById('scene');
const ctx = canvas.getContext('2d');
const BOUNDS = MODEL.atoms.reduce((bounds, atom) => ({{
  minX: Math.min(bounds.minX, atom.x),
  maxX: Math.max(bounds.maxX, atom.x),
  minY: Math.min(bounds.minY, atom.y),
  maxY: Math.max(bounds.maxY, atom.y),
  minZ: Math.min(bounds.minZ, atom.z),
  maxZ: Math.max(bounds.maxZ, atom.z)
}}), {{ minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity, minZ: Infinity, maxZ: -Infinity }});
const CENTER = {{
  x: (BOUNDS.minX + BOUNDS.maxX) / 2,
  y: (BOUNDS.minY + BOUNDS.maxY) / 2,
  z: (BOUNDS.minZ + BOUNDS.maxZ) / 2
}};
const MODEL_RADIUS = Math.max(
  1,
  ...MODEL.atoms.map(atom => Math.hypot(atom.x - CENTER.x, atom.y - CENTER.y, atom.z - CENTER.z))
);
let width = 0;
let height = 0;
let yaw = -0.85;
let pitch = 0.35;
let zoom = 1.18;
let dragging = false;
let lastX = 0;
let lastY = 0;

function resize() {{
  const ratio = window.devicePixelRatio || 1;
  width = Math.max(1, canvas.clientWidth);
  height = Math.max(1, canvas.clientHeight);
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
}}

function rotate(point) {{
  const cy = Math.cos(yaw), sy = Math.sin(yaw);
  const cp = Math.cos(pitch), sp = Math.sin(pitch);
  let x = point.x * cy + point.z * sy;
  let z = -point.x * sy + point.z * cy;
  let y = point.y * cp - z * sp;
  z = point.y * sp + z * cp;
  return {{ x, y, z }};
}}

function project(point) {{
  const centered = {{ x: point.x - CENTER.x, y: point.y - CENTER.y, z: point.z - CENTER.z }};
  const rotated = rotate(centered);
  const scale = zoom * Math.min(width, height) * 0.46 / MODEL_RADIUS;
  const cameraDistance = MODEL_RADIUS * 5.2;
  const perspective = cameraDistance / Math.max(1, cameraDistance - rotated.z);
  return {{
    x: width / 2 + rotated.x * scale * perspective,
    y: height / 2 - rotated.y * scale * perspective,
    z: rotated.z,
    size: scale * perspective
  }};
}}

function atomColor(atom) {{
  if (atom.group === 'ligand') return '#ff00d4';
  if (atom.element === 'P') return '#66c2ff';
  return '#0787ff';
}}

function bondColor(bond) {{
  return bond.group === 'ligand' ? '#ff00d4' : '#0787ff';
}}

function draw() {{
  ctx.clearRect(0, 0, width, height);
  const projected = new Map();
  for (const atom of MODEL.atoms) projected.set(atom.id, project(atom));

  const bonds = MODEL.bonds.slice().sort((left, right) => {{
    const leftZ = (projected.get(left.a).z + projected.get(left.b).z) / 2;
    const rightZ = (projected.get(right.a).z + projected.get(right.b).z) / 2;
    return leftZ - rightZ;
  }});

  ctx.lineCap = 'round';
  for (const bond of bonds) {{
    const a = projected.get(bond.a);
    const b = projected.get(bond.b);
    ctx.strokeStyle = bondColor(bond);
    ctx.globalAlpha = bond.group === 'basepair' ? 0.34 : 0.82;
    ctx.lineWidth = bond.group === 'dna_backbone' ? 5 : 2.2;
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.stroke();
  }}
  ctx.globalAlpha = 1;

  const atoms = MODEL.atoms.slice().sort((left, right) => projected.get(left.id).z - projected.get(right.id).z);
  for (const atom of atoms) {{
    const point = projected.get(atom.id);
    const radius = Math.max(atom.group === 'ligand' ? 2.8 : 3.3, point.size * (atom.group === 'ligand' ? 0.11 : 0.13));
    const gradient = ctx.createRadialGradient(point.x - radius * 0.4, point.y - radius * 0.4, radius * 0.1, point.x, point.y, radius);
    gradient.addColorStop(0, '#ffffff');
    gradient.addColorStop(0.22, atomColor(atom));
    gradient.addColorStop(1, atom.group === 'ligand' ? '#7e006f' : '#003d84');
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(point.x, point.y, radius, 0, Math.PI * 2);
    ctx.fill();
  }}
}}

function frame() {{
  if (!dragging) yaw += 0.002;
  draw();
  requestAnimationFrame(frame);
}}

canvas.addEventListener('pointerdown', event => {{
  dragging = true;
  lastX = event.clientX;
  lastY = event.clientY;
  canvas.setPointerCapture(event.pointerId);
}});
canvas.addEventListener('pointermove', event => {{
  if (!dragging) return;
  yaw += (event.clientX - lastX) * 0.008;
  pitch += (event.clientY - lastY) * 0.008;
  pitch = Math.max(-1.35, Math.min(1.35, pitch));
  lastX = event.clientX;
  lastY = event.clientY;
}});
canvas.addEventListener('pointerup', () => {{ dragging = false; }});
canvas.addEventListener('wheel', event => {{
  event.preventDefault();
  zoom *= event.deltaY > 0 ? 0.92 : 1.08;
  zoom = Math.max(0.45, Math.min(2.8, zoom));
}}, {{ passive: false }});

window.addEventListener('resize', resize);
resize();
frame();
</script>
</body>
</html>
"""


def _add_dna_duplex(atoms: list[ModelAtom], bonds: list[ModelBond], sequence: str, complement: str) -> None:
    top_sugar_serials: list[int] = []
    bottom_sugar_serials: list[int] = []
    for index, base in enumerate(sequence):
        theta = math.radians(index * TWIST_DEGREES)
        z = index * RISE
        top = _add_nucleotide(atoms, bonds, base, "A", index + 1, theta, z, "forward")
        bottom_base = complement[index]
        bottom = _add_nucleotide(atoms, bonds, bottom_base, "B", len(sequence) - index, theta + math.pi, z, "reverse")
        top_sugar_serials.append(top["sugar"])
        bottom_sugar_serials.append(bottom["sugar"])
        bonds.append(ModelBond(top["base"], bottom["base"], "basepair"))

    for first, second in zip(top_sugar_serials, top_sugar_serials[1:]):
        bonds.append(ModelBond(first, second, "dna_backbone"))
    for first, second in zip(bottom_sugar_serials, bottom_sugar_serials[1:]):
        bonds.append(ModelBond(first, second, "dna_backbone"))


def _add_nucleotide(
    atoms: list[ModelAtom],
    bonds: list[ModelBond],
    base: str,
    chain: str,
    residue_number: int,
    theta: float,
    z: float,
    direction: str,
) -> dict[str, int]:
    residue = f"D{base}"
    radial = (math.cos(theta), math.sin(theta), 0.0)
    tangent = (-math.sin(theta), math.cos(theta), 0.0)
    phosphate = _point(radial, 10.2, tangent, 0.32 if direction == "forward" else -0.32, z - 0.38)
    sugar = _point(radial, 8.45, tangent, -0.18 if direction == "forward" else 0.18, z)
    base_point = _point(radial, 4.25, tangent, 0.0, z + 0.08)

    p_serial = _append_atom(atoms, "P", "P", residue, chain, residue_number, phosphate, "dna")
    sugar_serial = _append_atom(atoms, "C1'", "C", residue, chain, residue_number, sugar, "dna")
    base_atom = "N9" if base in {"A", "G"} else "N1"
    base_serial = _append_atom(atoms, base_atom, "N", residue, chain, residue_number, base_point, "dna")
    bonds.append(ModelBond(p_serial, sugar_serial, "dna_backbone"))
    bonds.append(ModelBond(sugar_serial, base_serial, "dna_base"))
    return {"phosphate": p_serial, "sugar": sugar_serial, "base": base_serial}


def _add_polyamide_ligand(
    atoms: list[ModelAtom],
    bonds: list[ModelBond],
    design: PolyamideDesign,
    *,
    target_start_index: int,
) -> None:
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("RDKit is required for 3D model generation.") from exc

    mol = build_rdkit_polyamide_mol(design)
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 61453
    params.useSmallRingTorsions = True
    status = AllChem.EmbedMolecule(mol, params)
    if status == 0:
        try:
            AllChem.UFFOptimizeMolecule(mol, maxIters=250)
        except Exception:
            pass
    else:
        AllChem.Compute2DCoords(mol)

    mol = Chem.RemoveHs(mol)
    conf = mol.GetConformer()
    raw_coords = [
        (conf.GetAtomPosition(atom_index).x, conf.GetAtomPosition(atom_index).y, conf.GetAtomPosition(atom_index).z)
        for atom_index in range(mol.GetNumAtoms())
    ]
    fitted = _fit_ligand_to_minor_groove(
        raw_coords,
        len(design.sequence),
        target_start_index=target_start_index,
    )
    first_serial = len(atoms) + 1
    element_counts: dict[str, int] = {}

    for atom_index, atom in enumerate(mol.GetAtoms()):
        element = atom.GetSymbol()
        element_counts[element] = element_counts.get(element, 0) + 1
        name = f"{element}{element_counts[element]}"
        _append_atom(atoms, name, element, "PIP", "L", 1, fitted[atom_index], "ligand")

    for bond in mol.GetBonds():
        bonds.append(
            ModelBond(
                first_serial + bond.GetBeginAtomIdx(),
                first_serial + bond.GetEndAtomIdx(),
                "ligand",
            )
        )


def _fit_ligand_to_minor_groove(
    coords: list[tuple[float, float, float]],
    base_count: int,
    *,
    target_start_index: int,
) -> list[tuple[float, float, float]]:
    if not coords:
        return []

    center = tuple(sum(point[axis] for point in coords) / len(coords) for axis in range(3))
    spans = [
        max(point[axis] for point in coords) - min(point[axis] for point in coords)
        for axis in range(3)
    ]
    axes = sorted(range(3), key=lambda axis: spans[axis], reverse=True)
    major, secondary, tertiary = axes
    site_span = max(RISE, (base_count - 1) * RISE)
    major_scale = min(1.35, site_span / max(spans[major], 1.0))
    lateral_scale = major_scale * 0.62
    mid_index = target_start_index + (base_count - 1) / 2
    minor_radius = 5.75

    fitted = []
    for point in coords:
        local_index = mid_index + (point[major] - center[major]) * major_scale / RISE
        theta = math.radians(local_index * TWIST_DEGREES) - math.pi / 2
        radial = (math.cos(theta), math.sin(theta), 0.0)
        tangent = (-math.sin(theta), math.cos(theta), 0.0)
        lateral = (point[secondary] - center[secondary]) * lateral_scale
        radial_offset = (point[tertiary] - center[tertiary]) * lateral_scale * 0.7
        z = local_index * RISE
        fitted.append(
            _add3(
                _scale3(radial, minor_radius + radial_offset),
                _add3(_scale3(tangent, lateral), (0.0, 0.0, z)),
            )
        )
    return fitted


def _md_engine_status() -> dict:
    openmm_available = _module_available("openmm")
    amber_available = shutil.which("pmemd.cuda") is not None or shutil.which("pmemd") is not None
    ambertools_available = shutil.which("tleap") is not None and shutil.which("antechamber") is not None

    if openmm_available or amber_available:
        status = "engine_available_not_run"
        message = (
            "A local MD engine appears to be installed, but PIP Planner generated only the initial model "
            "and protocol notes. Production MD requires reviewed GAFF2 ligand parameters and charges."
        )
    else:
        status = "not_run"
        message = (
            "No supported local MD engine was detected. Generated an initial model plus protocol notes; "
            "no minimization, equilibration, or production MD trajectory was run."
        )

    return {
        "status": status,
        "engine": "Amber pmemd.cuda / OpenMM workflow",
        "openmm_available": openmm_available,
        "amber_available": amber_available,
        "ambertools_available": ambertools_available,
        "message": message,
        "sampling_recommendation": "Multiple independent replicas, hundreds of ns each, ideally microsecond-scale for selectivity claims.",
        "affinity_note": "Use alchemical free energy or restrained PMF/umbrella sampling for quantitative affinity; MM-PBSA is only a rough screen.",
    }


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
    except ImportError:
        return False
    return True


def _append_atom(
    atoms: list[ModelAtom],
    name: str,
    element: str,
    residue: str,
    chain: str,
    residue_number: int,
    point: tuple[float, float, float],
    group: str,
) -> int:
    serial = len(atoms) + 1
    atoms.append(
        ModelAtom(
            serial=serial,
            name=name,
            element=element,
            residue=residue,
            chain=chain,
            residue_number=residue_number,
            x=point[0],
            y=point[1],
            z=point[2],
            group=group,
        )
    )
    return serial


def _point(
    radial: tuple[float, float, float],
    radial_scale: float,
    tangent: tuple[float, float, float],
    tangent_scale: float,
    z: float,
) -> tuple[float, float, float]:
    return _add3(_scale3(radial, radial_scale), _add3(_scale3(tangent, tangent_scale), (0.0, 0.0, z)))


def _add3(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale3(a: tuple[float, float, float], factor: float) -> tuple[float, float, float]:
    return (a[0] * factor, a[1] * factor, a[2] * factor)
