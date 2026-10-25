# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure-Python tests for the corner bracket catalogue. FreeCAD is not required."""

import unittest

from freecad.TSlotWorkbench import Brackets
from freecad.TSlotWorkbench.Brackets import BracketDefinition
from freecad.TSlotWorkbench.Profiles import ProfileError

GOOD = dict(size="T", series=20.0, leg=18.0, width=18.0, wall=3.0, hole_width=4.5, hole_length=7.0, hole_start=7.7)


class TestCatalogue(unittest.TestCase):

    def test_sizes(self):
        self.assertEqual(Brackets.sizes(), ["20", "30", "40"])

    def test_rexroth_dimensions(self):
        # size: (leg, width, wall, hole width, slot end from the corner)
        expected = {"20": (18.0, 18.0, 3.0, 4.5, 14.7), "30": (27.0, 28.0, 6.0, 6.4, 20.0),
                    "40": (36.0, 38.0, 5.5, 8.7, 29.5)}
        for size, (leg, width, wall, hole, end) in expected.items():
            with self.subTest(size=size):
                b = Brackets.get_bracket(size)
                self.assertEqual((b.leg, b.width, b.wall, b.hole_width), (leg, width, wall, hole))
                self.assertAlmostEqual(b.hole_end, end)

    def test_bracket_for_series(self):
        self.assertEqual(Brackets.bracket_for(20.0).size, "20")
        self.assertEqual(Brackets.bracket_for(30.0).size, "30")
        self.assertEqual(Brackets.bracket_for(40.0).size, "40")
        self.assertEqual(Brackets.bracket_for(45.0).size, "40")
        with self.assertRaises(ProfileError):
            Brackets.bracket_for(10.0)

    def test_unknown_size(self):
        with self.assertRaises(ProfileError):
            Brackets.get_bracket("45")

    def test_duplicate_rejected(self):
        with self.assertRaises(ProfileError):
            Brackets.register_bracket(Brackets.get_bracket("20"))


class TestInvalidBrackets(unittest.TestCase):

    def test_valid_reference(self):
        self.assertEqual(BracketDefinition(**GOOD).hole_end, 14.7)

    def test_bad_numbers(self):
        for name in ("series", "leg", "width", "wall", "hole_width", "hole_length", "hole_start"):
            for value in (0, -1.0, float("inf"), "3", None, True):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ProfileError):
                        BracketDefinition(**{**GOOD, name: value})

    def test_inconsistent(self):
        for change in (dict(wall=18.0), dict(hole_length=4.0), dict(hole_start=2.0),
                       dict(hole_start=12.0), dict(hole_width=12.0, hole_length=12.0, hole_start=3.0)):
            with self.subTest(change=change):
                with self.assertRaises(ProfileError):
                    BracketDefinition(**{**GOOD, **change})


if __name__ == "__main__":
    unittest.main()
