from __future__ import annotations

from dataclasses import dataclass
import math

from .model import PolyamideDesign


class ChemistryRendererError(RuntimeError):
    """Raised when the chemistry toolkit cannot build or draw a design."""


@dataclass(frozen=True)
class ChemicalRendering:
    svg: str
    canonical_smiles: str
    renderer: str
    note: str


@dataclass(frozen=True)
class _MonomerAtoms:
    label: str
    ring: tuple[int, int, int, int, int]
    methyl: int
    carbonyl_c: int
    carbonyl_o: int
    in_n: int
    hp_oxygen: int | None


@dataclass(frozen=True)
class _TurnAtoms:
    in_n: int
    methylenes: tuple[int, ...]
    carbonyl_c: int
    carbonyl_o: int


@dataclass(frozen=True)
class _TailAtoms:
    anchor_carbonyl: int | None
    amide_n: int
    carbons: tuple[int, ...]
    tertiary_n: int
    methyls: tuple[int, int]


@dataclass(frozen=True)
class _TerminalAmideAtoms:
    anchor_carbonyl: int | None
    terminal_n: int


@dataclass(frozen=True)
class _BuiltPolyamide:
    mol: object
    monomers: tuple[_MonomerAtoms, ...]
    turn: _TurnAtoms | None
    tail: _TailAtoms | None
    terminal_amides: tuple[_TerminalAmideAtoms, ...]


def render_rdkit_chemical_svg(design: PolyamideDesign) -> ChemicalRendering:
    try:
        from rdkit import Chem
        from rdkit.Chem.Draw import rdMolDraw2D
        from rdkit.Geometry import Point3D
        from rdkit import rdBase
    except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing.
        raise ChemistryRendererError(
            "RDKit is required for chemical SVG rendering. Install it with: python -m pip install rdkit"
        ) from exc

    built = _build_rdkit_polyamide(design)
    mol = built.mol
    mol.SetProp("_Name", f"PIP {design.sequence} {design.options.architecture}")
    _assign_polyamide_figure_coords(mol, built, design, Point3D)

    width = max(900, 95 * max(6, len(design.chain_monomers)))
    height = 520 if design.options.architecture == "hairpin" else 380
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    options = drawer.drawOptions()
    options.legendFontSize = 18
    options.padding = 0.08
    options.addStereoAnnotation = True
    options.includeMetadata = True
    options.useBWAtomPalette()
    options.singleColourBonds = True
    options.singleColourWedgeBonds = True
    options.standardColoursForHighlightedAtoms = False
    options.setLegendColour((0, 0, 0))
    options.setSymbolColour((0, 0, 0))
    options.setAnnotationColour((0, 0, 0))
    options.setAtomNoteColour((0, 0, 0))
    options.setBondNoteColour((0, 0, 0))
    options.setHighlightColour((0, 0, 0))
    options.setQueryColour((0, 0, 0))
    options.setVariableAttachmentColour((0, 0, 0))

    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()

    svg = drawer.GetDrawingText()
    if "RDKit" not in svg:
        svg = svg.replace("<svg", "<svg data-renderer=\"RDKit\"", 1)

    return ChemicalRendering(
        svg=svg,
        canonical_smiles=Chem.MolToSmiles(mol, canonical=True),
        renderer=f"RDKit {rdBase.rdkitVersion}",
        note=(
            "Chemical SVG generated from an RDKit molecular graph for the Py/Im/Hp "
            "polyamide planning structure. Confirm terminal/cap choices before synthesis."
        ),
    )


def build_rdkit_polyamide_mol(design: PolyamideDesign):
    return _build_rdkit_polyamide(design).mol


def _build_rdkit_polyamide(design: PolyamideDesign) -> _BuiltPolyamide:
    try:
        from rdkit import Chem
    except ImportError as exc:  # pragma: no cover
        raise ChemistryRendererError(
            "RDKit is required for chemical structure generation."
        ) from exc

    builder = _PolyamideMolBuilder(Chem)

    if design.options.architecture == "hairpin":
        residues = list(design.top_monomers)
        for residue in residues:
            builder.add_monomer(residue)

        if design.options.turn == "gamma":
            builder.add_alkyl_turn(3)
        elif design.options.turn == "beta":
            builder.add_alkyl_turn(2)

        for residue in reversed(design.bottom_monomers):
            builder.add_monomer(residue)
    else:
        for residue in design.top_monomers:
            builder.add_monomer(residue)

    if design.options.tail == "dp":
        builder.add_dp_tail()
    else:
        builder.add_terminal_amide()

    mol = builder.finish()
    try:
        Chem.SanitizeMol(mol)
    except Exception as exc:
        raise ChemistryRendererError(f"RDKit could not sanitize the generated molecule: {exc}") from exc
    return _BuiltPolyamide(
        mol=mol,
        monomers=tuple(builder.monomers),
        turn=builder.turn,
        tail=builder.tail,
        terminal_amides=tuple(builder.terminal_amides),
    )


def _assign_polyamide_figure_coords(mol, built: _BuiltPolyamide, design: PolyamideDesign, point_cls) -> None:
    coords: list[tuple[float, float] | None] = [None] * mol.GetNumAtoms()
    monomers = built.monomers
    if not monomers:
        return

    if design.options.architecture == "hairpin":
        top_count = len(design.top_monomers)
        bottom_count = len(monomers) - top_count
        spacing = 3.25
        tangent = _unit((1.0, 0.34))
        normal = _perp(tangent)
        strand_gap = 4.80
        top_origin = _scale(normal, strand_gap / 2)
        bottom_origin = _scale(normal, -strand_gap / 2)

        for index, monomer in enumerate(monomers[:top_count]):
            center = _add(top_origin, _scale(tangent, index * spacing))
            monomer_normal = normal if index % 2 == 0 else _scale(normal, -1.0)
            _place_monomer(coords, monomer, center, tangent, monomer_normal)

        for index, monomer in enumerate(monomers[top_count:]):
            center = _add(bottom_origin, _scale(tangent, (bottom_count - 1 - index) * spacing))
            bottom_normal = _scale(normal, -1.0)
            monomer_normal = bottom_normal if index % 2 == 0 else normal
            _place_monomer(coords, monomer, center, _scale(tangent, -1.0), monomer_normal)

        if built.turn and len(monomers) > top_count:
            _place_turn(coords, built.turn, monomers[top_count - 1], monomers[top_count], side="right")
        terminal_direction = _scale(tangent, -1.0)
    else:
        spacing = 3.35
        tangent = _unit((1.0, -0.13))
        normal = _perp(tangent)
        for index, monomer in enumerate(monomers):
            center = _add(_scale(tangent, index * spacing), _scale(normal, _stagger(index, 0.08)))
            monomer_normal = normal if index % 2 == 0 else _scale(normal, -1.0)
            _place_monomer(coords, monomer, center, tangent, monomer_normal)
        terminal_direction = tangent

    _place_tail(coords, built.tail, monomers, terminal_direction)
    _place_terminal_amides(coords, built.terminal_amides, monomers, terminal_direction)
    _refine_carbonyl_oxygens(mol, coords, built)
    _fill_missing_coords(mol, coords)

    conf = mol.GetConformer() if mol.GetNumConformers() else None
    if conf is None:
        from rdkit import Chem

        conf = Chem.Conformer(mol.GetNumAtoms())
        conf.Set3D(False)
        conf_id = mol.AddConformer(conf, assignId=True)
        conf = mol.GetConformer(conf_id)

    for atom_index, xy in enumerate(coords):
        x, y = xy or (0.0, 0.0)
        conf.SetAtomPosition(atom_index, point_cls(float(x), float(y), 0.0))


def _place_monomer(
    coords: list[tuple[float, float] | None],
    monomer: _MonomerAtoms,
    center: tuple[float, float],
    tangent: tuple[float, float],
    normal: tuple[float, float],
) -> None:
    tangent = _unit(tangent)
    normal = _unit(normal)

    local_ring = [
        (-0.03, 0.84),
        (0.79, 0.29),
        (0.52, -0.66),
        (-0.47, -0.70),
        (-0.81, 0.23),
    ]
    ring_coords = []
    for atom_index, local_xy in zip(monomer.ring, local_ring):
        xy = _from_local(center, tangent, normal, local_xy)
        coords[atom_index] = xy
        ring_coords.append(xy)

    ring0, _ring1, ring2, _ring3, _ring4 = ring_coords
    coords[monomer.methyl] = _from_local(center, tangent, normal, (-0.05, 1.56))
    coords[monomer.carbonyl_c] = _from_local(center, tangent, normal, (1.52, 0.55))
    coords[monomer.carbonyl_o] = _from_local(center, tangent, normal, (1.66, 1.32))
    coords[monomer.in_n] = _from_local(center, tangent, normal, (-1.05, -1.45))

    if monomer.hp_oxygen is not None:
        coords[monomer.hp_oxygen] = _from_local(center, tangent, normal, (0.95, -1.22))


def _place_turn(
    coords: list[tuple[float, float] | None],
    turn: _TurnAtoms,
    top_anchor_monomer: _MonomerAtoms,
    bottom_anchor_monomer: _MonomerAtoms,
    side: str,
) -> None:
    top_anchor = coords[top_anchor_monomer.carbonyl_c]
    bottom_anchor = coords[bottom_anchor_monomer.in_n]
    if top_anchor is None or bottom_anchor is None:
        return

    direction = 1.0 if side == "right" else -1.0
    exit_direction = _carbonyl_exit_direction(coords, top_anchor_monomer, (direction, -0.65))
    coords[turn.in_n] = _add(top_anchor, _scale(exit_direction, 0.92))
    side_vector = _unit((direction, 0.10))
    carbonyl_direction = _unit((direction, 0.28 if bottom_anchor[1] < top_anchor[1] else -0.28))
    carbonyl = _add(bottom_anchor, _scale(carbonyl_direction, 0.92))

    start = coords[turn.in_n]
    control_offset = max(0.95, abs(start[1] - carbonyl[1]) * 0.22)
    control_one = _add(start, _scale(side_vector, control_offset))
    control_two = _add(carbonyl, _scale(side_vector, control_offset))
    turn_axis = _unit(_sub(carbonyl, start))
    zigzag_vector = _perp(turn_axis)

    for index, atom_index in enumerate(turn.methylenes):
        fraction = (index + 1) / (len(turn.methylenes) + 1)
        point = _cubic_bezier(start, control_one, control_two, carbonyl, fraction)
        point = _add(point, _scale(zigzag_vector, 0.22 if index % 2 == 0 else -0.22))
        coords[atom_index] = point

    coords[turn.carbonyl_c] = carbonyl
    coords[turn.carbonyl_o] = (carbonyl[0] + direction * 0.50, carbonyl[1] - 0.38)


def _place_tail(
    coords: list[tuple[float, float] | None],
    tail: _TailAtoms | None,
    monomers: tuple[_MonomerAtoms, ...],
    direction_hint: tuple[float, float],
) -> None:
    if tail is None:
        return

    anchor = coords[tail.anchor_carbonyl] if tail.anchor_carbonyl is not None else None
    if anchor is None:
        anchor = coords[monomers[-1].carbonyl_c] or (0.0, 0.0)

    anchor_monomer = _monomer_for_carbonyl(monomers, tail.anchor_carbonyl)
    direction = _carbonyl_exit_direction(coords, anchor_monomer, direction_hint)
    normal = _perp(direction)
    cursor = _add(anchor, _scale(direction, 0.92))
    coords[tail.amide_n] = cursor

    previous = cursor
    for index, atom_index in enumerate(tail.carbons):
        offset = 0.36 if index % 2 == 0 else -0.36
        point = _add(_add(previous, _scale(direction, 0.96)), _scale(normal, offset))
        coords[atom_index] = point
        previous = point

    offset = 0.36 if len(tail.carbons) % 2 == 0 else -0.36
    cursor = _add(_add(previous, _scale(direction, 0.96)), _scale(normal, offset))
    coords[tail.tertiary_n] = cursor

    previous_direction = _unit(_sub(previous, cursor))
    coords[tail.methyls[0]] = _add(cursor, _scale(_rotate(previous_direction, 120), 0.66))
    coords[tail.methyls[1]] = _add(cursor, _scale(_rotate(previous_direction, -120), 0.66))


def _place_terminal_amides(
    coords: list[tuple[float, float] | None],
    terminal_amides: tuple[_TerminalAmideAtoms, ...],
    monomers: tuple[_MonomerAtoms, ...],
    direction_hint: tuple[float, float],
) -> None:
    for terminal in terminal_amides:
        anchor = coords[terminal.anchor_carbonyl] if terminal.anchor_carbonyl is not None else None
        if anchor is None:
            anchor = (0.0, 0.0)
        anchor_monomer = _monomer_for_carbonyl(monomers, terminal.anchor_carbonyl)
        direction = _carbonyl_exit_direction(coords, anchor_monomer, direction_hint)
        coords[terminal.terminal_n] = _add(anchor, _scale(direction, 0.92))


def _monomer_for_carbonyl(
    monomers: tuple[_MonomerAtoms, ...],
    carbonyl_index: int | None,
) -> _MonomerAtoms | None:
    if carbonyl_index is None:
        return None
    for monomer in monomers:
        if monomer.carbonyl_c == carbonyl_index:
            return monomer
    return None


def _refine_carbonyl_oxygens(
    mol,
    coords: list[tuple[float, float] | None],
    built: _BuiltPolyamide,
) -> None:
    carbonyls = [(monomer.carbonyl_c, monomer.carbonyl_o) for monomer in built.monomers]
    if built.turn is not None:
        carbonyls.append((built.turn.carbonyl_c, built.turn.carbonyl_o))

    for carbonyl_c, carbonyl_o in carbonyls:
        carbonyl_xy = coords[carbonyl_c]
        if carbonyl_xy is None:
            continue
        neighbor_vectors = []
        for neighbor in mol.GetAtomWithIdx(carbonyl_c).GetNeighbors():
            neighbor_index = neighbor.GetIdx()
            if neighbor_index == carbonyl_o or coords[neighbor_index] is None:
                continue
            neighbor_vectors.append(_unit(_sub(coords[neighbor_index], carbonyl_xy)))
        if len(neighbor_vectors) < 2:
            continue

        bisector = _add(neighbor_vectors[0], neighbor_vectors[1])
        if math.hypot(*bisector) < 0.001:
            oxygen_direction = _perp(neighbor_vectors[0])
        else:
            oxygen_direction = _scale(_unit(bisector), -1.0)
        coords[carbonyl_o] = _add(carbonyl_xy, _scale(oxygen_direction, 0.78))


def _carbonyl_exit_direction(
    coords: list[tuple[float, float] | None],
    monomer: _MonomerAtoms | None,
    fallback: tuple[float, float],
) -> tuple[float, float]:
    if monomer is None:
        return _unit(fallback)

    carbonyl = coords[monomer.carbonyl_c]
    ring_atom = coords[monomer.ring[1]]
    oxygen = coords[monomer.carbonyl_o]
    if carbonyl is None or ring_atom is None or oxygen is None:
        return _unit(fallback)

    ring_vector = _unit(_sub(ring_atom, carbonyl))
    oxygen_vector = _unit(_sub(oxygen, carbonyl))
    exit_vector = _scale(_add(ring_vector, oxygen_vector), -1.0)
    if math.hypot(*exit_vector) < 0.001:
        return _unit(fallback)
    return _unit(exit_vector)


def _fill_missing_coords(mol, coords: list[tuple[float, float] | None]) -> None:
    for atom_index, xy in enumerate(coords):
        if xy is not None:
            continue
        atom = mol.GetAtomWithIdx(atom_index)
        neighbor_points = [
            coords[neighbor.GetIdx()]
            for neighbor in atom.GetNeighbors()
            if coords[neighbor.GetIdx()] is not None
        ]
        if neighbor_points:
            base = neighbor_points[0]
            coords[atom_index] = (base[0] + 0.45, base[1] + 0.45)
        else:
            coords[atom_index] = (0.0, 0.0)


def _stagger(index: int, amount: float) -> float:
    return amount if index % 2 == 0 else -amount


def _add(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] + b[0], a[1] + b[1])


def _sub(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    return (a[0] - b[0], a[1] - b[1])


def _scale(a: tuple[float, float], factor: float) -> tuple[float, float]:
    return (a[0] * factor, a[1] * factor)


def _from_local(
    origin: tuple[float, float],
    tangent: tuple[float, float],
    normal: tuple[float, float],
    local_xy: tuple[float, float],
) -> tuple[float, float]:
    return _add(_add(origin, _scale(tangent, local_xy[0])), _scale(normal, local_xy[1]))


def _cubic_bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    fraction: float,
) -> tuple[float, float]:
    inverse = 1.0 - fraction
    return (
        inverse**3 * p0[0]
        + 3 * inverse**2 * fraction * p1[0]
        + 3 * inverse * fraction**2 * p2[0]
        + fraction**3 * p3[0],
        inverse**3 * p0[1]
        + 3 * inverse**2 * fraction * p1[1]
        + 3 * inverse * fraction**2 * p2[1]
        + fraction**3 * p3[1],
    )


def _perp(a: tuple[float, float]) -> tuple[float, float]:
    return (-a[1], a[0])


def _rotate(a: tuple[float, float], degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    cos_value = math.cos(radians)
    sin_value = math.sin(radians)
    return (
        a[0] * cos_value - a[1] * sin_value,
        a[0] * sin_value + a[1] * cos_value,
    )


def _unit(a: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(a[0], a[1])
    if length == 0:
        return (1.0, 0.0)
    return (a[0] / length, a[1] / length)


class _PolyamideMolBuilder:
    def __init__(self, chem_module):
        self.Chem = chem_module
        self.mol = chem_module.RWMol()
        self.pending_carbonyl: int | None = None
        self._last_carbonyl_oxygen: int | None = None
        self.monomers: list[_MonomerAtoms] = []
        self.turn: _TurnAtoms | None = None
        self.tail: _TailAtoms | None = None
        self.terminal_amides: list[_TerminalAmideAtoms] = []

    def add_monomer(self, label: str) -> None:
        in_n, out_c = self._add_heteroaromatic_monomer(label)
        self._connect_pending_to(in_n)
        self.pending_carbonyl = out_c

    def add_alkyl_turn(self, methylene_count: int) -> None:
        anchor = self.pending_carbonyl
        in_n = self._add_atom("N")
        self._connect_pending_to(in_n)
        previous = in_n
        methylenes = []
        for _ in range(methylene_count):
            carbon = self._add_atom("C")
            self._bond(previous, carbon)
            previous = carbon
            methylenes.append(carbon)
        out_c = self._add_carbonyl(previous)
        self.pending_carbonyl = out_c
        self.turn = _TurnAtoms(
            in_n=in_n,
            methylenes=tuple(methylenes),
            carbonyl_c=out_c,
            carbonyl_o=self._last_carbonyl_oxygen,
        )

    def add_dp_tail(self) -> None:
        anchor = self.pending_carbonyl
        amide_n = self._add_atom("N")
        self._connect_pending_to(amide_n)
        previous = amide_n
        carbons = []
        for _ in range(3):
            carbon = self._add_atom("C")
            self._bond(previous, carbon)
            previous = carbon
            carbons.append(carbon)
        tertiary_n = self._add_atom("N")
        self._bond(previous, tertiary_n)
        methyl_1 = self._add_atom("C")
        methyl_2 = self._add_atom("C")
        self._bond(tertiary_n, methyl_1)
        self._bond(tertiary_n, methyl_2)
        self.tail = _TailAtoms(
            anchor_carbonyl=anchor,
            amide_n=amide_n,
            carbons=tuple(carbons),
            tertiary_n=tertiary_n,
            methyls=(methyl_1, methyl_2),
        )
        self.pending_carbonyl = None

    def add_terminal_amide(self) -> None:
        anchor = self.pending_carbonyl
        terminal_n = self._add_atom("N")
        self._connect_pending_to(terminal_n)
        self.terminal_amides.append(
            _TerminalAmideAtoms(anchor_carbonyl=anchor, terminal_n=terminal_n)
        )
        self.pending_carbonyl = None

    def finish(self):
        if self.pending_carbonyl is not None:
            self.add_terminal_amide()
        return self.mol.GetMol()

    def _add_heteroaromatic_monomer(self, label: str) -> tuple[int, int]:
        if label == "Im":
            ring = [
                self._add_aromatic_atom("N"),
                self._add_aromatic_atom("C"),
                self._add_aromatic_atom("N"),
                self._add_aromatic_atom("C"),
                self._add_aromatic_atom("C"),
            ]
        else:
            ring = [
                self._add_aromatic_atom("N"),
                self._add_aromatic_atom("C"),
                self._add_aromatic_atom("C"),
                self._add_aromatic_atom("C"),
                self._add_aromatic_atom("C"),
            ]

        for first, second in zip(ring, [*ring[1:], ring[0]]):
            self._bond(first, second, self.Chem.BondType.AROMATIC)

        methyl = self._add_atom("C")
        self._bond(ring[0], methyl)
        out_c = self._add_carbonyl(ring[1])
        carbonyl_o = self._last_carbonyl_oxygen
        in_n = self._add_atom("N")
        self._bond(ring[3], in_n)

        hp_oxygen = None
        if label == "Hp":
            hp_oxygen = self._add_atom("O")
            self._bond(ring[2], hp_oxygen)

        self.monomers.append(
            _MonomerAtoms(
                label=label,
                ring=tuple(ring),  # type: ignore[arg-type]
                methyl=methyl,
                carbonyl_c=out_c,
                carbonyl_o=carbonyl_o,
                in_n=in_n,
                hp_oxygen=hp_oxygen,
            )
        )

        return in_n, out_c

    def _add_carbonyl(self, attach_to: int) -> int:
        carbonyl_c = self._add_atom("C")
        oxygen = self._add_atom("O")
        self._bond(attach_to, carbonyl_c)
        self._bond(carbonyl_c, oxygen, self.Chem.BondType.DOUBLE)
        self._last_carbonyl_oxygen = oxygen
        return carbonyl_c

    def _connect_pending_to(self, atom_index: int) -> None:
        if self.pending_carbonyl is not None:
            self._bond(self.pending_carbonyl, atom_index)

    def _add_atom(self, symbol: str) -> int:
        return self.mol.AddAtom(self.Chem.Atom(symbol))

    def _add_aromatic_atom(self, symbol: str) -> int:
        atom = self.Chem.Atom(symbol)
        atom.SetIsAromatic(True)
        return self.mol.AddAtom(atom)

    def _bond(self, begin: int, end: int, bond_type=None) -> None:
        self.mol.AddBond(begin, end, bond_type or self.Chem.BondType.SINGLE)
