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

    legend = (
        f"{design.options.architecture}; {design.chain_code}; "
        "RDKit 2D depiction"
    )
    drawer.DrawMolecule(mol, legend=legend)
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
        spacing = 3.0
        top_y = 1.95
        bottom_y = -1.95

        for index, monomer in enumerate(monomers[:top_count]):
            center = ((top_count - 1 - index) * spacing, top_y + _stagger(index, 0.16))
            _place_monomer(coords, monomer, center, math.pi)

        for index, monomer in enumerate(monomers[top_count:]):
            center = (index * spacing, bottom_y - _stagger(index, 0.16))
            _place_monomer(coords, monomer, center, 0.0)

        if built.turn and len(monomers) > top_count:
            _place_turn(coords, built.turn, monomers[top_count - 1], monomers[top_count])
    else:
        spacing = 2.85
        for index, monomer in enumerate(monomers):
            center = (index * spacing, -0.48 * index + _stagger(index, 0.10))
            _place_monomer(coords, monomer, center, 0.0)

    _place_tail(coords, built.tail, monomers)
    _place_terminal_amides(coords, built.terminal_amides)
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
    angle: float,
) -> None:
    radius = 0.68
    base_angles = [90, 18, -54, -126, 162]
    ring_coords = []
    for atom_index, degrees in zip(monomer.ring, base_angles):
        theta = math.radians(degrees) + angle
        xy = (center[0] + radius * math.cos(theta), center[1] + radius * math.sin(theta))
        coords[atom_index] = xy
        ring_coords.append(xy)

    ring0, ring1, ring2, ring3, _ring4 = ring_coords
    methyl_vector = _unit(_sub(ring0, center))
    out_vector = _unit(_sub(ring1, center))
    in_vector = _unit(_sub(ring3, center))

    coords[monomer.methyl] = _add(ring0, _scale(methyl_vector, 0.54))
    coords[monomer.carbonyl_c] = _add(ring1, _scale(out_vector, 0.72))
    coords[monomer.carbonyl_o] = _add(
        coords[monomer.carbonyl_c],
        _scale(out_vector, 0.62),
    )
    coords[monomer.in_n] = _add(ring3, _scale(in_vector, 0.66))

    if monomer.hp_oxygen is not None:
        coords[monomer.hp_oxygen] = _add(ring2, _scale(_unit(_sub(ring2, center)), 0.56))


def _place_turn(
    coords: list[tuple[float, float] | None],
    turn: _TurnAtoms,
    top_left: _MonomerAtoms,
    bottom_left: _MonomerAtoms,
) -> None:
    top_anchor = coords[top_left.carbonyl_c]
    bottom_anchor = coords[bottom_left.in_n]
    if top_anchor is None or bottom_anchor is None:
        return

    left_x = min(top_anchor[0], bottom_anchor[0]) - 0.95
    middle_y = (top_anchor[1] + bottom_anchor[1]) / 2
    coords[turn.in_n] = (left_x + 0.24, top_anchor[1] - 0.22)

    if len(turn.methylenes) == 3:
        methylene_points = [
            (left_x - 0.40, top_anchor[1] - 0.72),
            (left_x - 0.68, middle_y),
            (left_x - 0.40, bottom_anchor[1] + 0.72),
        ]
    elif len(turn.methylenes) == 2:
        methylene_points = [
            (left_x - 0.52, top_anchor[1] - 0.76),
            (left_x - 0.52, bottom_anchor[1] + 0.76),
        ]
    else:
        methylene_points = [
            (left_x - 0.58, top_anchor[1] + (bottom_anchor[1] - top_anchor[1]) * (index + 1) / (len(turn.methylenes) + 1))
            for index in range(len(turn.methylenes))
        ]

    for atom_index, point in zip(turn.methylenes, methylene_points):
        coords[atom_index] = point

    carbonyl = (left_x + 0.24, bottom_anchor[1] + 0.22)

    coords[turn.carbonyl_c] = carbonyl
    coords[turn.carbonyl_o] = (carbonyl[0] - 0.50, carbonyl[1] - 0.38)


def _place_tail(
    coords: list[tuple[float, float] | None],
    tail: _TailAtoms | None,
    monomers: tuple[_MonomerAtoms, ...],
) -> None:
    if tail is None:
        return

    anchor = coords[tail.anchor_carbonyl] if tail.anchor_carbonyl is not None else None
    if anchor is None:
        anchor = coords[monomers[-1].carbonyl_c] or (0.0, 0.0)

    direction = _unit((1.0, -0.18))
    normal = _perp(direction)
    cursor = _add(anchor, _scale(direction, 1.02))
    coords[tail.amide_n] = cursor

    for atom_index in tail.carbons:
        cursor = _add(cursor, _scale(direction, 0.94))
        coords[atom_index] = cursor

    cursor = _add(cursor, _scale(direction, 0.94))
    coords[tail.tertiary_n] = cursor
    coords[tail.methyls[0]] = _add(cursor, _scale(normal, 0.58))
    coords[tail.methyls[1]] = _add(cursor, _scale(normal, -0.58))


def _place_terminal_amides(
    coords: list[tuple[float, float] | None],
    terminal_amides: tuple[_TerminalAmideAtoms, ...],
) -> None:
    for terminal in terminal_amides:
        anchor = coords[terminal.anchor_carbonyl] if terminal.anchor_carbonyl is not None else None
        if anchor is None:
            anchor = (0.0, 0.0)
        coords[terminal.terminal_n] = _add(anchor, (0.72, -0.12))


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


def _perp(a: tuple[float, float]) -> tuple[float, float]:
    return (-a[1], a[0])


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
