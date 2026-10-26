# SPDX-License-Identifier: LGPL-2.1-or-later
"""Tests for the angle bracket and foot catalogues (pure Python), and for the parts in FreeCAD."""

import unittest

from freecad.TSlotWorkbench import MountingCatalogue as Catalogue
from freecad.TSlotWorkbench.Profiles import ProfileError

try:
    import FreeCAD
except ImportError:
    FreeCAD = None

if FreeCAD is not None:
    from freecad.TSlotWorkbench import CornerBracket, Extrusion, Hardware, Mounting

GOOD = dict(size="T", series=20.0, width=20.0, leg=20.0, reach=18.0, wall=3.0, hole_width=4.5,
            hole_length=8.0, plate_hole=3.5)


class TestCatalogue(unittest.TestCase):

    def test_sizes(self):
        self.assertEqual(Catalogue.angle_bracket_sizes(), ["20", "30", "40"])
        self.assertEqual(Catalogue.foot_threads(), ["M5", "M6", "M8", "M10"])

    def test_lookup(self):
        self.assertEqual(Catalogue.angle_bracket_for(40).size, "40")
        self.assertEqual(Catalogue.angle_bracket_for(25).size, "20")
        with self.assertRaises(ProfileError):
            Catalogue.angle_bracket_for(10)
        with self.assertRaises(ProfileError):
            Catalogue.get_angle_bracket("50")
        with self.assertRaises(ProfileError):
            Catalogue.get_foot("M3")

    def test_default_foot_thread(self):
        self.assertEqual([Catalogue.foot_for(u) for u in (20, 30, 40)], ["M5", "M6", "M8"])

    def test_invalid_definitions(self):
        for change in ({"wall": 12.0}, {"hole_length": 3.0}, {"hole_length": 25.0}, {"hole_width": 12.0},
                       {"plate_hole": 11.0}, {"reach": -1.0}, {"width": float("nan")}, {"size": ""}):
            with self.subTest(change=change), self.assertRaises(ProfileError):
                Catalogue.AngleBracketDefinition(**{**GOOD, **change})
        Catalogue.AngleBracketDefinition(**GOOD)
        with self.assertRaises(ProfileError):
            Catalogue.FootDefinition("M8", 8.0, pad_diameter=6.0, pad_thickness=5.0, engage=10.0)
        with self.assertRaises(ProfileError):
            Catalogue.register_foot(Catalogue.get_foot("M8"))


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class MountingTestCase(unittest.TestCase):

    def setUp(self):
        self.doc = FreeCAD.newDocument("TSlotMountingTest")
        # A 4040 along +X from 0 to 500, centred on the X axis.
        self.base = Extrusion.make_extrusion(self.doc, length=500, family="B-Type")
        self.base.Placement = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90))
        self.doc.recompute()

    def tearDown(self):
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)

    def assertClean(self, obj):
        self.assertTrue(obj.isValid(), obj.getStatusString())
        self.assertFalse({"Touched", "Invalid", "Error"} & set(obj.State), (obj.Label, obj.State))


class TestAngleBracket(MountingTestCase):

    def side_facing_up(self):
        for side in Hardware.SIDES:
            frame = Hardware.slot_frame(self.base, side, 0, 100.0)
            if frame.Rotation.multVec(FreeCAD.Vector(0, 0, 1)).z > 0.99:
                return side

    def test_shape_and_placement(self):
        side = self.side_facing_up()
        bracket = Mounting.make_angle_bracket(self.doc, self.base, side, 0, 100.0, direction="+Y")
        self.doc.recompute()
        self.assertClean(bracket)
        spec = Catalogue.get_angle_bracket("40")
        box = bracket.Shape.BoundBox
        self.assertAlmostEqual(box.XLength, spec.width, delta=1e-6)
        self.assertEqual(len(bracket.Shape.Solids), 1)
        self.assertEqual(bracket.BendOffset.Value, 20.0)  # the edge of a 40 mm face
        self.assertLess(bracket.Shape.common(self.base.Shape).Volume, 1e-3)
        # Leg A lies on the face: touching it, and the ledge stands out of it.
        self.assertAlmostEqual(bracket.Shape.distToShape(self.base.Shape)[0], 0.0, delta=1e-6)
        self.assertAlmostEqual(box.ZMin, 20.0, delta=1e-6)  # on the top face, which this side faces
        self.assertAlmostEqual(box.ZMax, 20.0 + spec.reach, delta=1e-6)  # the ledge stands out of it

    def test_ledge_is_flush_with_the_top_when_the_face_is_vertical(self):
        for side in Hardware.SIDES:
            frame = Hardware.slot_frame(self.base, side, 0, 100.0)
            if abs(frame.Rotation.multVec(FreeCAD.Vector(0, 0, 1)).z) < 0.01:  # a vertical face
                bracket = Mounting.make_angle_bracket(self.doc, self.base, side, 0, 100.0)
                self.doc.recompute()
                self.assertClean(bracket)
                self.assertAlmostEqual(bracket.Shape.BoundBox.ZMax, 20.0, delta=1e-6)  # the top of the extrusion
                self.assertEqual(bracket.Direction, Mounting.default_direction(self.base, side, 0, 100.0))
                self.doc.removeObject(bracket.Name)

    def test_direction_mirrors_the_bracket(self):
        a = Mounting.make_angle_bracket(self.doc, self.base, "+Y", 0, 100.0, direction="+Y")
        b = Mounting.make_angle_bracket(self.doc, self.base, "+Y", 0, 100.0, direction="-Y")
        self.doc.recompute()
        self.assertAlmostEqual(a.Shape.Volume, b.Shape.Volume, delta=1e-6)
        self.assertGreater(abs(a.Shape.CenterOfMass.x - b.Shape.CenterOfMass.x) + abs(a.Shape.CenterOfMass.z - b.Shape.CenterOfMass.z), 1.0)

    def test_hardware_follows_the_bracket(self):
        bracket = Mounting.make_angle_bracket(self.doc, self.base, "+Y", 0, 100.0)
        nut, screw = Mounting.make_angle_bracket_hardware(self.doc, bracket)
        self.doc.recompute()
        self.assertClean(nut)
        self.assertEqual(nut.Thread, "M8")  # the 40 bracket's screw, which a B-Type 4040 slot takes
        self.assertEqual(CornerBracket.nuts_of(bracket), [nut])
        bracket.Position = 250.0
        self.doc.recompute()
        self.assertAlmostEqual(nut.Position.Value, 250.0, delta=1e-6)
        self.assertClean(nut)
        self.assertLess(nut.Shape.common(self.base.Shape).Volume, 1e-3)
        if screw is not None:
            self.assertClean(screw)
            self.assertEqual(Hardware.screws_of(nut), [screw])

    def test_invalid_arguments(self):
        with self.assertRaises(Mounting.Profiles.ProfileError):
            Mounting.make_angle_bracket(self.doc, self.base, "+Y", 3, 100.0)
        with self.assertRaises(Mounting.Profiles.ProfileError):
            Mounting.make_angle_bracket(self.doc, self.base, "+Y", 0, 100.0, direction="up")
        short = Mounting.make_angle_bracket(self.doc, self.base, "+Y", 0, 100.0, bend=2.0)
        self.doc.recompute()
        self.assertIn("Invalid", short.State)  # the bend is too close to the slot

    def test_save_reopen(self):
        import os
        import tempfile

        bracket = Mounting.make_angle_bracket(self.doc, self.base, "+Y", 0, 100.0)
        Mounting.make_angle_bracket_hardware(self.doc, bracket)
        self.doc.recompute()
        path = os.path.join(tempfile.mkdtemp(), "a.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        doc = FreeCAD.openDocument(path)
        doc.recompute()
        for obj in doc.Objects:
            self.assertTrue(obj.isValid(), obj.Label)
        (restored,) = [o for o in doc.Objects if isinstance(getattr(o, "Proxy", None), Mounting.AngleBracket)]
        self.assertEqual(restored.BracketSize, "40")


class TestFoot(MountingTestCase):

    def test_foot_at_each_end(self):
        for end, z in (("End", 500.0), ("Start", 0.0)):
            with self.subTest(end=end):
                foot = Mounting.make_foot(self.doc, self.base, end, extension=30.0)
                self.doc.recompute()
                self.assertClean(foot)
                self.assertEqual(len(foot.Shape.Solids), 1)
                self.assertLess(foot.Shape.common(self.base.Shape).Volume, 1e-3)
                box = foot.Shape.BoundBox
                spec = Catalogue.get_foot(foot.Thread)
                # Pad centre and bottom: the extension plus the pad, out of the end along the axis (global X).
                if end == "End":
                    self.assertAlmostEqual(box.XMax, z + 30.0 + spec.pad_thickness, delta=1e-6)
                else:
                    self.assertAlmostEqual(box.XMin, z - 30.0 - spec.pad_thickness, delta=1e-6)
                self.assertAlmostEqual(box.YLength, spec.pad_diameter, delta=1e-6)
                self.doc.removeObject(foot.Name)

    def test_extension_levels_the_foot(self):
        foot = Mounting.make_foot(self.doc, self.base, "End", extension=20.0)
        self.doc.recompute()
        before = foot.Shape.BoundBox.XMax
        foot.Extension = 45.0
        self.doc.recompute()
        self.assertAlmostEqual(foot.Shape.BoundBox.XMax - before, 25.0, delta=1e-6)

    def test_one_foot_per_bore(self):
        wide = Extrusion.make_extrusion(self.doc, size="8080", length=300)
        self.doc.recompute()
        feet = Mounting.make_feet(self.doc, wide, "End")
        self.doc.recompute()
        self.assertEqual(len(feet), 4)
        for foot in feet:
            self.assertClean(foot)
            self.assertLess(foot.Shape.common(wide.Shape).Volume, 1e-3)
        self.assertEqual(len({(round(f.Placement.Base.x, 3), round(f.Placement.Base.y, 3)) for f in feet}), 4)

    def test_default_thread_follows_the_series(self):
        for size, thread in (("2020", "M5"), ("3030", "M6"), ("4040", "M8"), ("8080", "M8")):
            with self.subTest(size=size):
                ext = Extrusion.make_extrusion(self.doc, size=size, length=200)
                foot = Mounting.make_foot(self.doc, ext, "End")
                self.doc.recompute()
                self.assertEqual(foot.Thread, thread)
                self.assertClean(foot)
                self.assertLess(foot.Shape.common(ext.Shape).Volume, 1e-3)

    def test_lower_end_and_bad_arguments(self):
        self.assertEqual(Mounting.lower_end(self.base), "Start")  # runs along +X, so Z is 0 at both ends: start
        upright = Extrusion.make_extrusion(self.doc, length=300)
        self.assertEqual(Mounting.lower_end(upright), "Start")
        upright.Placement = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180))
        self.assertEqual(Mounting.lower_end(upright), "End")
        for kwargs in ({"end": "Top"}, {"end": "End", "bore": 4}, {"end": "End", "thread": "M3"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(Mounting.Profiles.ProfileError):
                Mounting.make_foot(self.doc, upright, **kwargs)


class TestDeleteWithMounting(MountingTestCase):

    def test_attached_to_includes_the_new_parts(self):
        bracket = Mounting.make_angle_bracket(self.doc, self.base, "+Y", 0, 100.0)
        nut, screw = Mounting.make_angle_bracket_hardware(self.doc, bracket)
        foot = Mounting.make_foot(self.doc, self.base, "End")
        self.doc.recompute()
        screws, nuts, parts = CornerBracket.attached_to([self.base])
        self.assertEqual({o.Name for o in parts}, {bracket.Name, foot.Name})
        self.assertEqual([n.Name for n in nuts], [nut.Name])
        self.assertEqual([s.Name for s in screws], [screw.Name] if screw is not None else [])
