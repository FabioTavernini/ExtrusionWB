# SPDX-License-Identifier: LGPL-2.1-or-later
"""Geometry tests for the T-slot cross-section (run with tools/run_tests.sh).

These probe the actual shape: line sections across each slot, point
containment, and the bore's surface. Under plain Python they are skipped.
"""

import math
import unittest

try:
    import FreeCAD
    import Part
except ImportError:
    FreeCAD = None

if FreeCAD is not None:
    from freecad.TSlotWorkbench import Geometry, Profiles

SIZES = ("2020", "3030", "4040")
TOL = 1e-6


def rotate(x, y, quarter_turns):
    """Rotate (x, y) clockwise about Z by 90 degrees per quarter turn."""
    for _ in range(quarter_turns % 4):
        x, y = y, -x
    return x, y


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class TestGeometry(unittest.TestCase):

    FAMILY = "Generic"

    def profile(self, size):
        return Profiles.get_profile(self.FAMILY, size)

    def side_point(self, profile, side, u, v, z=0.0):
        """Point at (u along the side, v deep from the face) on side 0..3 (top, right, bottom, left)."""
        x, y = rotate(u, profile.outer / 2.0 - v, side)
        return FreeCAD.Vector(x, y, z)

    def gaps_across_side(self, profile, face, side, v):
        """Lengths of the empty stretches of a line along ``side`` at depth ``v``."""
        half = profile.outer / 2.0
        line = Part.makeLine(self.side_point(profile, side, -half, v),
                             self.side_point(profile, side, half, v))
        return sorted(e.Length for e in line.cut(face).Edges)

    def test_valid_single_solid(self):
        for size in SIZES:
            with self.subTest(size=size):
                shape = Geometry.create_extrusion_shape(self.profile(size), 500)
                self.assertFalse(shape.isNull())
                self.assertTrue(shape.isValid())
                self.assertEqual(len(shape.Solids), 1)
                self.assertEqual(len(shape.Shells), 1)
                self.assertTrue(shape.isClosed())
                self.assertGreater(shape.Volume, 0.0)
                shape.check(True)  # full BOP check: raises on self-intersection etc.

    def test_face_is_valid_with_one_hole(self):
        for size in SIZES:
            with self.subTest(size=size):
                face = Geometry.create_profile_face(self.profile(size))
                self.assertTrue(face.isValid())
                self.assertEqual(len(face.Wires), 2)  # outline + bore
                self.assertTrue(face.OuterWire.isClosed())
                self.assertEqual(len(face.OuterWire.Edges), 4 * 11)
                face.check(True)

    def test_outer_dimensions_and_length(self):
        for size in SIZES:
            for length in (1.0, 750.0, 3000.0):
                with self.subTest(size=size, length=length):
                    p = self.profile(size)
                    bb = Geometry.create_extrusion_shape(p, length).BoundBox
                    half = p.outer / 2.0
                    self.assertAlmostEqual(bb.XMin, -half, delta=TOL)
                    self.assertAlmostEqual(bb.XMax, half, delta=TOL)
                    self.assertAlmostEqual(bb.YMin, -half, delta=TOL)
                    self.assertAlmostEqual(bb.YMax, half, delta=TOL)
                    self.assertAlmostEqual(bb.ZMin, 0.0, delta=TOL)
                    self.assertAlmostEqual(bb.ZMax, length, delta=TOL)

    def test_four_undercut_slots(self):
        """Each side has exactly one opening, with a wider cavity behind its lips."""
        for size in SIZES:
            p = self.profile(size)
            s = p.slot
            face = Geometry.create_profile_face(p)
            for side in range(4):
                with self.subTest(size=size, side=side):
                    opening = self.gaps_across_side(p, face, side, s.lip / 2.0)
                    cavity = self.gaps_across_side(p, face, side, s.lip + s.cavity_height / 2.0)
                    self.assertEqual(len(opening), 1)
                    self.assertEqual(len(cavity), 1)
                    self.assertAlmostEqual(opening[0], s.opening, delta=TOL)
                    self.assertAlmostEqual(cavity[0], s.cavity_width, delta=TOL)
                    self.assertGreater(cavity[0], opening[0])

                    # A point under the lip: material in the lip, empty behind it.
                    u = (s.opening + s.cavity_width) / 4.0
                    in_lip = self.side_point(p, side, u, s.lip / 2.0)
                    behind_lip = self.side_point(p, side, u, s.lip + s.cavity_height / 2.0)
                    self.assertTrue(face.isInside(in_lip, TOL, True))
                    self.assertFalse(face.isInside(behind_lip, TOL, True))

                    # The slot floor is closed: solid just below it, nothing beyond it.
                    self.assertTrue(face.isInside(self.side_point(p, side, 0.0, s.depth + 0.1), TOL, True))
                    self.assertFalse(face.isInside(self.side_point(p, side, 0.0, s.depth - 0.1), TOL, True))

    def test_no_grooves_away_from_slots(self):
        """Corners are solid: only the slot opening breaks each outer face."""
        for size in SIZES:
            p = self.profile(size)
            face = Geometry.create_profile_face(p)
            half = p.outer / 2.0
            for side in range(4):
                with self.subTest(size=size, side=side):
                    corner = self.side_point(p, side, -(half + p.slot.opening / 2.0) / 2.0, 0.05)
                    self.assertTrue(face.isInside(corner, TOL, True))

    def test_central_bore_runs_full_length(self):
        length = 400.0
        for size in SIZES:
            with self.subTest(size=size):
                p = self.profile(size)
                shape = Geometry.create_extrusion_shape(p, length)
                radius = p.bore_diameter / 2.0
                cylinders = [f for f in shape.Faces if isinstance(f.Surface, Part.Cylinder)]
                self.assertTrue(cylinders)
                for f in cylinders:
                    self.assertAlmostEqual(f.Surface.Radius, radius, delta=TOL)
                    self.assertAlmostEqual(f.BoundBox.ZLength, length, delta=TOL)
                self.assertAlmostEqual(sum(f.Area for f in cylinders), math.pi * p.bore_diameter * length,
                                       delta=1e-6 * length)
                for z in (0.0, 0.5, length / 2.0, length - 0.5, length):
                    self.assertFalse(shape.isInside(FreeCAD.Vector(0, 0, z), TOL, True))
                    # Material directly around the bore.
                    self.assertTrue(shape.isInside(FreeCAD.Vector(radius + 0.5, 0, z), TOL, True))

    def test_length_changes_only_z(self):
        p = self.profile("3030")
        short = Geometry.create_extrusion_shape(p, 100)
        long = Geometry.create_extrusion_shape(p, 1000)
        self.assertAlmostEqual(long.Volume, 10 * short.Volume, delta=1e-6 * long.Volume)
        self.assertAlmostEqual(long.BoundBox.ZLength, 1000, delta=TOL)
        for a, b in ((short.BoundBox.XLength, long.BoundBox.XLength), (short.BoundBox.YLength, long.BoundBox.YLength)):
            self.assertAlmostEqual(a, b, delta=TOL)

    def test_sizes_have_different_sections(self):
        areas = [Geometry.create_profile_face(self.profile(size)).Area for size in SIZES]
        self.assertEqual(len(set(round(a, 6) for a in areas)), 3)
        self.assertEqual(areas, sorted(areas))

    def test_regeneration_is_repeatable(self):
        for size in SIZES:
            with self.subTest(size=size):
                a = Geometry.create_extrusion_shape(self.profile(size), 750)
                b = Geometry.create_extrusion_shape(self.profile(size), 750)
                self.assertEqual(len(a.Faces), len(b.Faces))
                self.assertAlmostEqual(a.Volume, b.Volume, delta=TOL)
                points = lambda s: sorted((round(v.X, 9), round(v.Y, 9), round(v.Z, 9)) for v in s.Vertexes)
                self.assertEqual(points(a), points(b))
                self.assertLess(a.cut(b).Volume, 1e-6)

    def test_section_has_fourfold_symmetry(self):
        for size in SIZES:
            with self.subTest(size=size):
                face = Geometry.create_profile_face(self.profile(size))
                turned = face.copy()
                turned.rotate(FreeCAD.Vector(), FreeCAD.Vector(0, 0, 1), 90)
                self.assertLess(face.cut(turned).Area, 1e-6)

    def test_rejects_bad_length(self):
        for length in (0, -10):
            with self.assertRaises(Profiles.ProfileError):
                Geometry.create_extrusion_shape(self.profile("4040"), length)


class TestBTypeGeometry(TestGeometry):
    """The same checks for the B-Type profiles."""

    FAMILY = "B-Type"


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class TestMultiUnitGeometry(unittest.TestCase):
    """Wider profiles: a slot on every outer unit edge, a bore in every unit."""

    CASES = [(family, size) for family in ("Generic", "B-Type")
             for size in ("2040", "2060", "3090", "4080", "40120", "8080")]

    def slot_gaps(self, profile, face, along_x, offset, v):
        """Empty stretches of a line along one long side, ``v`` deep from it.

        ``along_x`` picks the top/bottom face (line along X) or a side face
        (line along Y); ``offset`` is that face's coordinate.
        """
        inward = -1.0 if offset > 0 else 1.0
        c = offset + inward * v
        if along_x:
            a, b = FreeCAD.Vector(-profile.width / 2.0, c, 0), FreeCAD.Vector(profile.width / 2.0, c, 0)
        else:
            a, b = FreeCAD.Vector(c, -profile.height / 2.0, 0), FreeCAD.Vector(c, profile.height / 2.0, 0)
        return Part.makeLine(a, b).cut(face).Edges

    def test_valid_solid_and_size(self):
        for family, size in self.CASES:
            with self.subTest(family=family, size=size):
                p = Profiles.get_profile(family, size)
                shape = Geometry.create_extrusion_shape(p, 300)
                self.assertTrue(shape.isValid())
                self.assertEqual(len(shape.Solids), 1)
                shape.check(True)
                bb = shape.BoundBox
                self.assertAlmostEqual(bb.XLength, p.width, delta=TOL)
                self.assertAlmostEqual(bb.YLength, p.height, delta=TOL)
                self.assertAlmostEqual(bb.Center.x, 0.0, delta=TOL)
                self.assertAlmostEqual(bb.Center.y, 0.0, delta=TOL)

    def test_one_slot_per_unit_edge(self):
        for family, size in self.CASES:
            p = Profiles.get_profile(family, size)
            s = p.slot
            face = Geometry.create_profile_face(p)
            for along_x, offset, units in ((True, p.height / 2.0, p.columns), (True, -p.height / 2.0, p.columns),
                                           (False, p.width / 2.0, p.rows), (False, -p.width / 2.0, p.rows)):
                with self.subTest(family=family, size=size, along_x=along_x, offset=offset):
                    openings = self.slot_gaps(p, face, along_x, offset, s.lip / 2.0)
                    cavities = self.slot_gaps(p, face, along_x, offset, s.lip + s.cavity_height / 2.0)
                    self.assertEqual(len(openings), units)
                    self.assertEqual(len(cavities), units)
                    for e in openings:
                        self.assertAlmostEqual(e.Length, s.opening, delta=TOL)
                    for e in cavities:
                        self.assertAlmostEqual(e.Length, s.cavity_width, delta=TOL)

    def test_one_bore_per_unit(self):
        for family, size in self.CASES:
            with self.subTest(family=family, size=size):
                p = Profiles.get_profile(family, size)
                face = Geometry.create_profile_face(p)
                self.assertEqual(len(face.Wires), 1 + p.columns * p.rows)
                self.assertEqual(len(face.OuterWire.Edges), 4 + 20 * (p.columns + p.rows))
                for x, y in Geometry.bore_centres(p):
                    self.assertFalse(face.isInside(FreeCAD.Vector(x, y, 0), TOL, True))
                    self.assertTrue(face.isInside(FreeCAD.Vector(x + p.bore_diameter / 2.0 + 0.5, y, 0), TOL, True))

    def test_rows_run_along_y(self):
        p = Profiles.get_profile("B-Type", "2040")
        self.assertEqual(sorted(Geometry.bore_centres(p)), [(0.0, -10.0), (0.0, 10.0)])


if __name__ == "__main__":
    unittest.main()
