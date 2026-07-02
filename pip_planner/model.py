from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Literal


Architecture = Literal["hairpin", "linear"]
AtMode = Literal["distinguish", "py-py"]
Tail = Literal["dp", "none"]
Turn = Literal["gamma", "beta", "none"]


COMPLEMENT = {
    "A": "T",
    "T": "A",
    "G": "C",
    "C": "G",
}

PAIRING_CODE_DISTINGUISH = {
    "A": ("A-T", "Py", "Hp"),
    "T": ("T-A", "Hp", "Py"),
    "G": ("G-C", "Im", "Py"),
    "C": ("C-G", "Py", "Im"),
}

PAIRING_CODE_PY_PY = {
    "A": ("A-T", "Py", "Py"),
    "T": ("T-A", "Py", "Py"),
    "G": ("G-C", "Im", "Py"),
    "C": ("C-G", "Py", "Im"),
}

TURN_LABELS = {
    "gamma": "gamma-turn",
    "beta": "beta-turn",
    "none": "turn",
}

TAIL_LABELS = {
    "dp": "Dp",
    "none": "",
}


@dataclass(frozen=True)
class DesignOptions:
    architecture: Architecture = "hairpin"
    at_mode: AtMode = "distinguish"
    tail: Tail = "dp"
    turn: Turn = "gamma"


@dataclass(frozen=True)
class BasePairDesign:
    position: int
    target_base: str
    complement_base: str
    base_pair: str
    top_monomer: str
    bottom_monomer: str

    @property
    def monomer_pair(self) -> str:
        return f"{self.top_monomer}/{self.bottom_monomer}"


@dataclass(frozen=True)
class PolyamideDesign:
    sequence: str
    complement: str
    options: DesignOptions
    base_pairs: tuple[BasePairDesign, ...]
    chain_monomers: tuple[str, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def top_monomers(self) -> tuple[str, ...]:
        return tuple(pair.top_monomer for pair in self.base_pairs)

    @property
    def bottom_monomers(self) -> tuple[str, ...]:
        return tuple(pair.bottom_monomer for pair in self.base_pairs)

    @property
    def monomer_pairs(self) -> tuple[str, ...]:
        return tuple(pair.monomer_pair for pair in self.base_pairs)

    @property
    def chain_code(self) -> str:
        return "-".join(self.chain_monomers)

    def to_dict(self) -> dict:
        return {
            "sequence": self.sequence,
            "sequence_label": f"5'-{self.sequence}-3'",
            "complement": self.complement,
            "complement_label": f"3'-{self.complement}-5'",
            "architecture": self.options.architecture,
            "at_mode": self.options.at_mode,
            "tail": self.options.tail,
            "turn": self.options.turn,
            "recognition_pairs": list(self.monomer_pairs),
            "top_monomers": list(self.top_monomers),
            "bottom_monomers": list(self.bottom_monomers),
            "chain_monomers": list(self.chain_monomers),
            "chain_code": self.chain_code,
            "base_pairs": [
                {
                    "position": pair.position,
                    "target_base": pair.target_base,
                    "complement_base": pair.complement_base,
                    "base_pair": pair.base_pair,
                    "monomer_pair": pair.monomer_pair,
                    "top_monomer": pair.top_monomer,
                    "bottom_monomer": pair.bottom_monomer,
                }
                for pair in self.base_pairs
            ],
            "warnings": list(self.warnings),
        }


class SequenceValidationError(ValueError):
    """Raised when user DNA input cannot be interpreted as A/T/G/C DNA."""


def normalize_dna(raw_sequence: str) -> str:
    """Normalize direct DNA or FASTA-like input to an uppercase A/T/G/C string."""
    if raw_sequence is None:
        raise SequenceValidationError("DNA sequence is required.")

    sequence_lines = []
    for raw_line in str(raw_sequence).splitlines():
        line = raw_line.strip()
        if not line or line.startswith(">"):
            continue
        sequence_lines.append(line)

    cleaned = "".join(sequence_lines).upper()
    cleaned = re.sub(r"[\s\-'_]", "", cleaned)
    cleaned = cleaned.replace("5", "").replace("3", "")

    if not cleaned:
        raise SequenceValidationError("DNA sequence is empty after normalization.")

    invalid = sorted(set(cleaned) - set(COMPLEMENT))
    if invalid:
        invalid_text = ", ".join(invalid)
        raise SequenceValidationError(
            f"DNA sequence can only contain A, T, G, and C. Invalid character(s): {invalid_text}."
        )

    return cleaned


def design_polyamide(raw_sequence: str, options: DesignOptions | None = None) -> PolyamideDesign:
    options = options or DesignOptions()
    sequence = normalize_dna(raw_sequence)
    complement = "".join(COMPLEMENT[base] for base in sequence)
    code = PAIRING_CODE_PY_PY if options.at_mode == "py-py" else PAIRING_CODE_DISTINGUISH

    base_pairs = tuple(
        BasePairDesign(
            position=index + 1,
            target_base=base,
            complement_base=COMPLEMENT[base],
            base_pair=code[base][0],
            top_monomer=code[base][1],
            bottom_monomer=code[base][2],
        )
        for index, base in enumerate(sequence)
    )

    top = tuple(pair.top_monomer for pair in base_pairs)
    bottom = tuple(pair.bottom_monomer for pair in base_pairs)
    tail_label = TAIL_LABELS[options.tail]

    if options.architecture == "hairpin":
        turn_label = TURN_LABELS[options.turn]
        chain = top + (turn_label,) + tuple(reversed(bottom))
    else:
        chain = top

    if tail_label:
        chain = chain + (tail_label,)

    warnings = list(_warnings_for_design(sequence, options))

    return PolyamideDesign(
        sequence=sequence,
        complement=complement,
        options=options,
        base_pairs=base_pairs,
        chain_monomers=chain,
        warnings=tuple(warnings),
    )


def _warnings_for_design(sequence: str, options: DesignOptions) -> tuple[str, ...]:
    warnings: list[str] = []

    if options.architecture == "hairpin" and len(sequence) > 5:
        warnings.append(
            "Hairpin PIPs are often designed for short recognition sites; confirm long sites with spacers, tandem motifs, or binding data."
        )

    if len(sequence) > 12:
        warnings.append(
            "This tool generates a design candidate, not an affinity/selectivity prediction. Long targets need experimental validation."
        )

    if options.architecture == "linear":
        warnings.append(
            "Linear mode uses the top monomer from each recognition pair as a planning representation. Confirm the intended binding stoichiometry before synthesis."
        )

    if options.at_mode == "py-py":
        warnings.append(
            "Py/Py mode treats A-T and T-A as degenerate. Use Hp mode when A/T orientation discrimination is required."
        )

    if options.architecture == "hairpin" and options.turn == "none":
        warnings.append(
            "Hairpin mode without a named turn is schematic only. Specify gamma or beta for a concrete planning motif."
        )

    return tuple(warnings)


def safe_design_name(sequence: str, architecture: str) -> str:
    cleaned = normalize_dna(sequence)
    prefix = cleaned[:24]
    if len(cleaned) > len(prefix):
        prefix = f"{prefix}-{len(cleaned)}bp"
    return f"{prefix.lower()}-{architecture}"


def ensure_output_dir(out_dir: str | Path) -> Path:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path
