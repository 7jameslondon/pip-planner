from __future__ import annotations

from dataclasses import dataclass

from .model import PolyamideDesign


class ChemistryRendererError(RuntimeError):
    """Raised when the chemistry toolkit cannot build or draw a design."""


@dataclass(frozen=True)
class ChemicalRendering:
    svg: str
    canonical_smiles: str
    renderer: str
    note: str


def render_rdkit_chemical_svg(design: PolyamideDesign) -> ChemicalRendering:
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D
        from rdkit import rdBase
    except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing.
        raise ChemistryRendererError(
            "RDKit is required for chemical SVG rendering. Install it with: python -m pip install rdkit"
        ) from exc

    mol = build_rdkit_polyamide_mol(design)
    mol.SetProp("_Name", f"PIP {design.sequence} {design.options.architecture}")
    AllChem.Compute2DCoords(mol)

    width = max(900, 95 * max(6, len(design.chain_monomers)))
    height = 520 if design.options.architecture == "hairpin" else 380
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    options = drawer.drawOptions()
    options.legendFontSize = 18
    options.padding = 0.08
    options.addStereoAnnotation = True
    options.includeMetadata = True

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
    return mol


class _PolyamideMolBuilder:
    def __init__(self, chem_module):
        self.Chem = chem_module
        self.mol = chem_module.RWMol()
        self.pending_carbonyl: int | None = None

    def add_monomer(self, label: str) -> None:
        in_n, out_c = self._add_heteroaromatic_monomer(label)
        self._connect_pending_to(in_n)
        self.pending_carbonyl = out_c

    def add_alkyl_turn(self, methylene_count: int) -> None:
        in_n = self._add_atom("N")
        self._connect_pending_to(in_n)
        previous = in_n
        for _ in range(methylene_count):
            carbon = self._add_atom("C")
            self._bond(previous, carbon)
            previous = carbon
        out_c = self._add_carbonyl(previous)
        self.pending_carbonyl = out_c

    def add_dp_tail(self) -> None:
        amide_n = self._add_atom("N")
        self._connect_pending_to(amide_n)
        previous = amide_n
        for _ in range(3):
            carbon = self._add_atom("C")
            self._bond(previous, carbon)
            previous = carbon
        tertiary_n = self._add_atom("N")
        self._bond(previous, tertiary_n)
        self._bond(tertiary_n, self._add_atom("C"))
        self._bond(tertiary_n, self._add_atom("C"))
        self.pending_carbonyl = None

    def add_terminal_amide(self) -> None:
        terminal_n = self._add_atom("N")
        self._connect_pending_to(terminal_n)
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

        self._bond(ring[0], self._add_atom("C"))
        out_c = self._add_carbonyl(ring[1])
        in_n = self._add_atom("N")
        self._bond(ring[3], in_n)

        if label == "Hp":
            oxygen = self._add_atom("O")
            self._bond(ring[2], oxygen)

        return in_n, out_c

    def _add_carbonyl(self, attach_to: int) -> int:
        carbonyl_c = self._add_atom("C")
        oxygen = self._add_atom("O")
        self._bond(attach_to, carbonyl_c)
        self._bond(carbonyl_c, oxygen, self.Chem.BondType.DOUBLE)
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
