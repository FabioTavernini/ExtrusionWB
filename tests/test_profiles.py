# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure-Python tests for the profile catalogue. FreeCAD is not required."""

import dataclasses
import math
import unittest

from freecad.TSlotWorkbench import Profiles
from freecad.TSlotWorkbench.Profiles import ProfileDefinition, ProfileError, SlotDefinition

# The illustrative dimensions the generic profiles must use.
EXPECTED = {
    # size: (outer, opening, cavity width, depth, bore)
    "2020": (20.0, 6.0, 10.0, 5.0, 4.0),
    "3030": (30.0, 8.0, 14.0, 7.0, 6.0),
    "4040": (40.0, 8.0, 16.0, 9.0, 7.0),
}

# B-Type dimensions (see Profiles.py for the source).
EXPECTED_B_TYPE = {
    # size: (outer, opening, cavity width, depth, bore)
    "2020": (20.0, 6.2, 12.0, 5.5, 5.5),
    "3030": (30.0, 8.0, 16.5, 9.0, 7.3),
    "4040": (40.0, 10.0, 20.1, 12.5, 10.0),
}

GOOD_SLOT = dict(opening=6.0, lip=1.5, cavity_width=10.0, cavity_height=1.5, floor_width=6.0, depth=5.0)


class TestCatalogue(unittest.TestCase):

    def test_supported_sizes(self):
        self.assertEqual(Profiles.families(), ["Generic", "B-Type"])
        sizes = ["2020", "2040", "2060", "3030", "3060", "3090", "4040", "4080", "40120", "8080"]
        self.assertEqual(Profiles.sizes("Generic"), sizes)
        self.assertEqual(Profiles.sizes("B-Type"), sizes)

    def test_multi_unit_profiles(self):
        """Wider profiles are grids of the matching unit profile, columns along X."""
        for family in Profiles.families():
            for size, unit, columns, rows in (("2040", "2020", 1, 2), ("2060", "2020", 1, 3),
                                              ("3090", "3030", 1, 3), ("40120", "4040", 1, 3),
                                              ("8080", "4040", 2, 2)):
                with self.subTest(family=family, size=size):
                    profile = Profiles.get_profile(family, size)
                    base = Profiles.get_profile(family, unit)
                    self.assertEqual((profile.columns, profile.rows), (columns, rows))
                    self.assertEqual(profile.outer, base.outer)
                    self.assertEqual(profile.slot, base.slot)
                    self.assertEqual(profile.bore_diameter, base.bore_diameter)
                    self.assertEqual((profile.width, profile.height), (base.outer * columns, base.outer * rows))

    def test_single_unit_by_default(self):
        profile = Profiles.get_profile("Generic", "4040")
        self.assertEqual((profile.columns, profile.rows, profile.width, profile.height), (1, 1, 40.0, 40.0))

    def test_dimension_lookup(self):
        for family, expected in (("Generic", EXPECTED), ("B-Type", EXPECTED_B_TYPE)):
            for size, (outer, opening, cavity, depth, bore) in expected.items():
                with self.subTest(family=family, size=size):
                    profile = Profiles.get_profile(family, size)
                    self.assertEqual(profile.family, family)
                    self.assertEqual(profile.outer, outer)
                    self.assertEqual(profile.slot.opening, opening)
                    self.assertEqual(profile.slot.cavity_width, cavity)
                    self.assertEqual(profile.slot.depth, depth)
                    self.assertEqual(profile.bore_diameter, bore)

    def test_slots_are_undercut(self):
        for family in Profiles.families():
            for size in Profiles.sizes(family):
                with self.subTest(family=family, size=size):
                    slot = Profiles.get_profile(family, size).slot
                    self.assertGreater(slot.cavity_width, slot.opening)
                    self.assertLess(slot.taper_start, slot.depth)

    def test_b_type_cavities_taper_at_45_degrees(self):
        for size in EXPECTED_B_TYPE:
            with self.subTest(size=size):
                s = Profiles.get_profile("B-Type", size).slot
                self.assertAlmostEqual((s.cavity_width - s.floor_width) / 2.0, s.depth - s.taper_start, places=2)

    def test_walls_are_consistent(self):
        """Slots, cavities and bore do not meet; every wall is at least MIN_WALL thick."""
        for family in Profiles.families():
            for size in Profiles.sizes(family):
                with self.subTest(family=family, size=size):
                    walls = Profiles.get_profile(family, size).wall_thicknesses()
                    self.assertEqual(set(walls), {"corner", "diagonal web", "core", "lip"})
                    for name, thickness in walls.items():
                        self.assertGreaterEqual(thickness, Profiles.MIN_WALL, name)

    def test_defaults_are_registered(self):
        profile = Profiles.get_profile(Profiles.DEFAULT_FAMILY, Profiles.DEFAULT_SIZE)
        self.assertEqual(profile.size, "4040")
        self.assertEqual(Profiles.DEFAULT_LENGTH, 750.0)

    def test_unknown_size(self):
        with self.assertRaises(ProfileError):
            Profiles.get_profile("Generic", "4545")

    def test_unknown_family(self):
        with self.assertRaises(ProfileError):
            Profiles.get_profile("Bosch", "4040")
        with self.assertRaises(ProfileError):
            Profiles.sizes("Bosch")

    def test_profile_error_is_value_error(self):
        self.assertTrue(issubclass(ProfileError, ValueError))

    def test_duplicate_registration_rejected(self):
        existing = Profiles.get_profile("Generic", "4040")
        with self.assertRaises(ProfileError):
            Profiles.register_profile(dataclasses.replace(existing))

    def test_register_rejects_non_definition(self):
        with self.assertRaises(ProfileError):
            Profiles.register_profile(("Generic", "5050", 50, 50))

    def test_definitions_are_immutable(self):
        profile = Profiles.get_profile("Generic", "2020")
        with self.assertRaises(AttributeError):
            profile.outer = 25.0
        with self.assertRaises(AttributeError):
            profile.slot.opening = 5.0


class TestInvalidSlots(unittest.TestCase):

    def test_bad_numbers(self):
        for field in GOOD_SLOT:
            for value in (0, -1.0, math.inf, math.nan, "6", None, True):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ProfileError):
                        SlotDefinition(**{**GOOD_SLOT, field: value})

    def test_cavity_must_be_wider_than_opening(self):
        """A plain rectangular groove is not a T-slot."""
        with self.assertRaises(ProfileError):
            SlotDefinition(**{**GOOD_SLOT, "cavity_width": 6.0})
        with self.assertRaises(ProfileError):
            SlotDefinition(**{**GOOD_SLOT, "cavity_width": 5.0, "floor_width": 4.0})

    def test_floor_not_wider_than_cavity(self):
        with self.assertRaises(ProfileError):
            SlotDefinition(**{**GOOD_SLOT, "floor_width": 11.0})

    def test_cavity_must_fit_above_floor(self):
        with self.assertRaises(ProfileError):
            SlotDefinition(**{**GOOD_SLOT, "cavity_height": 3.5})


class TestInvalidProfiles(unittest.TestCase):

    def make(self, outer=20.0, bore=4.0, **slot):
        return ProfileDefinition("Test", "X", outer, SlotDefinition(**{**GOOD_SLOT, **slot}), bore)

    def test_valid_reference(self):
        self.assertEqual(self.make().outer, 20.0)

    def test_bad_names(self):
        slot = SlotDefinition(**GOOD_SLOT)
        for family, size in (("", "2020"), ("   ", "2020"), ("Test", ""), (None, "2020"), ("Test", 2020)):
            with self.subTest(family=family, size=size):
                with self.assertRaises(ProfileError):
                    ProfileDefinition(family, size, 20.0, slot, 4.0)

    def test_bad_numbers(self):
        for value in (0, -20.0, math.inf, math.nan, "20", None, True):
            with self.subTest(value=value):
                with self.assertRaises(ProfileError):
                    self.make(outer=value)
                with self.assertRaises(ProfileError):
                    self.make(bore=value)

    def test_bad_grid(self):
        slot = SlotDefinition(**GOOD_SLOT)
        for value in (0, -1, 1.5, 2.0, "2", None, True):
            with self.subTest(value=value):
                with self.assertRaises(ProfileError):
                    ProfileDefinition("Test", "X", 20.0, slot, 4.0, columns=value)
                with self.assertRaises(ProfileError):
                    ProfileDefinition("Test", "X", 20.0, slot, 4.0, rows=value)

    def test_slot_must_be_slot_definition(self):
        with self.assertRaises(ProfileError):
            ProfileDefinition("Test", "X", 20.0, GOOD_SLOT, 4.0)

    def test_bore_hits_slot_floor(self):
        with self.assertRaisesRegex(ProfileError, "core"):
            self.make(bore=9.0)

    def test_neighbouring_slots_collide(self):
        with self.assertRaisesRegex(ProfileError, "diagonal web"):
            self.make(cavity_width=13.0, floor_width=8.0)

    def test_cavity_breaks_through_side(self):
        with self.assertRaises(ProfileError):
            self.make(outer=10.0, bore=1.0)


class TestLengthValidation(unittest.TestCase):

    def test_positive_lengths(self):
        self.assertEqual(Profiles.validate_length(750), 750.0)
        self.assertEqual(Profiles.validate_length("1200"), 1200.0)
        self.assertEqual(Profiles.validate_length(0.001), 0.001)

    def test_invalid_lengths(self):
        for length in (0, 0.0, -1, -750.0, math.inf, math.nan, None, "abc", True):
            with self.subTest(length=length):
                with self.assertRaises(ProfileError):
                    Profiles.validate_length(length)


if __name__ == "__main__":
    unittest.main()
