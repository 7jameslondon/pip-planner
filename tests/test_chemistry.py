import math
import unittest

from rdkit.Geometry import Point3D

import pip_planner.chemistry as chemistry
from pip_planner.model import DesignOptions, design_polyamide


class ChemistryLayoutTests(unittest.TestCase):
    def test_hairpin_coordinates_use_two_strand_polyamide_layout(self) -> None:
        design = design_polyamide("GTAC", DesignOptions(architecture="hairpin"))
        built = chemistry._build_rdkit_polyamide(design)
        chemistry._assign_polyamide_figure_coords(built.mol, built, design, Point3D)

        conf = built.mol.GetConformer()
        top_count = len(design.top_monomers)
        top_centers = [_center(conf, monomer.ring) for monomer in built.monomers[:top_count]]
        bottom_centers = [_center(conf, monomer.ring) for monomer in built.monomers[top_count:]]

        self.assertGreater(_average_y(top_centers), _average_y(bottom_centers) + 2.5)
        self.assertLess(top_centers[0][0], top_centers[-1][0])
        self.assertGreater(bottom_centers[0][0], bottom_centers[-1][0])

        turn_x = conf.GetAtomPosition(built.turn.in_n).x
        rightmost_monomer_x = max(point[0] for point in [*top_centers, *bottom_centers])
        self.assertGreater(turn_x, rightmost_monomer_x)

        for bond in built.mol.GetBonds():
            begin = conf.GetAtomPosition(bond.GetBeginAtomIdx())
            end = conf.GetAtomPosition(bond.GetEndAtomIdx())
            distance = ((begin.x - end.x) ** 2 + (begin.y - end.y) ** 2) ** 0.5
            self.assertGreater(distance, 0.05)
            self.assertLess(
                distance,
                1.70,
                "publication-style layout should avoid stretched connector bonds",
            )

        for atom in built.mol.GetAtoms():
            neighbors = [neighbor.GetIdx() for neighbor in atom.GetNeighbors()]
            if len(neighbors) < 2:
                continue
            for first_index, first_neighbor in enumerate(neighbors):
                for second_neighbor in neighbors[first_index + 1 :]:
                    angle = _bond_angle_degrees(conf, atom.GetIdx(), first_neighbor, second_neighbor)
                    self.assertGreater(
                        angle,
                        65.0,
                        "chemical layout should not collapse substituent angles",
                    )
                    self.assertLess(
                        angle,
                        165.0,
                        "chemical layout should avoid nearly straight amide/linker angles",
                    )

        for atom_index in [*built.turn.methylenes, *built.tail.carbons]:
            atom = built.mol.GetAtomWithIdx(atom_index)
            neighbors = [neighbor.GetIdx() for neighbor in atom.GetNeighbors()]
            self.assertEqual(len(neighbors), 2)
            cosine = _bond_angle_cosine(conf, atom_index, neighbors)
            self.assertLess(
                abs(cosine),
                0.95,
                "saturated linkers should use zig-zag coordinates instead of straight carbon-labeled runs",
            )


def _center(conf, atom_indices: tuple[int, ...]) -> tuple[float, float]:
    points = [conf.GetAtomPosition(atom_index) for atom_index in atom_indices]
    return (
        sum(point.x for point in points) / len(points),
        sum(point.y for point in points) / len(points),
    )


def _average_y(points: list[tuple[float, float]]) -> float:
    return sum(point[1] for point in points) / len(points)


def _bond_angle_cosine(conf, atom_index: int, neighbors: list[int]) -> float:
    center = conf.GetAtomPosition(atom_index)
    first = conf.GetAtomPosition(neighbors[0])
    second = conf.GetAtomPosition(neighbors[1])
    first_vector = (first.x - center.x, first.y - center.y)
    second_vector = (second.x - center.x, second.y - center.y)
    denominator = math.hypot(*first_vector) * math.hypot(*second_vector)
    return (
        first_vector[0] * second_vector[0] + first_vector[1] * second_vector[1]
    ) / denominator


def _bond_angle_degrees(conf, atom_index: int, first_neighbor: int, second_neighbor: int) -> float:
    center = conf.GetAtomPosition(atom_index)
    first = conf.GetAtomPosition(first_neighbor)
    second = conf.GetAtomPosition(second_neighbor)
    first_vector = (first.x - center.x, first.y - center.y)
    second_vector = (second.x - center.x, second.y - center.y)
    denominator = math.hypot(*first_vector) * math.hypot(*second_vector)
    cosine = (
        first_vector[0] * second_vector[0] + first_vector[1] * second_vector[1]
    ) / denominator
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


if __name__ == "__main__":
    unittest.main()
