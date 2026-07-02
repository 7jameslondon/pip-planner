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


def _center(conf, atom_indices: tuple[int, ...]) -> tuple[float, float]:
    points = [conf.GetAtomPosition(atom_index) for atom_index in atom_indices]
    return (
        sum(point.x for point in points) / len(points),
        sum(point.y for point in points) / len(points),
    )


def _average_y(points: list[tuple[float, float]]) -> float:
    return sum(point[1] for point in points) / len(points)


if __name__ == "__main__":
    unittest.main()
