# SPDX-License-Identifier: LGPL-2.1-or-later
"""T-nut and screw tests that need a real FreeCAD (run with tools/run_tests.sh).

Screw tests also need the Fasteners workbench, and are skipped without it.
The joint is the one from test_bracket_freecad: a 4040 base along +X, its
top face at Z = 20, and a post standing on it.
"""

import os
import shutil
import tempfile
import unittest

try:
    import FreeCAD
    import Part
except ImportError:
    FreeCAD = None

if FreeCAD is not None:
    from freecad.TSlotWorkbench import Brackets, CornerBracket, Extrusion, Hardware, Profiles

    HAVE_FASTENERS = Hardware.fasteners_available()
else:
    HAVE_FASTENERS = False

TOL = 1e-6
# Fasteners screws are built from faceted revolutions; allow a sliver of overlap.
OVERLAP = 1e-3


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class TestNutShape(unittest.TestCase):

    def test_fits_every_slot(self):
        for family in Profiles.families():
            for size in ("2020", "3030", "4040"):
                with self.subTest(family=family, size=size):
                    slot = Profiles.get_profile(family, size).slot
                    thread = Hardware.thread_for_slot(slot)
                    nut = Hardware.make_nut_shape(slot, thread)
                    self.assertTrue(nut.isValid())
                    bb = nut.BoundBox
                    self.assertAlmostEqual(bb.ZMax, -0.25 * slot.lip, delta=TOL)
                    self.assertAlmostEqual(bb.ZMin, -(slot.depth - Hardware.FLOOR_CLEARANCE), delta=TOL)
                    self.assertAlmostEqual(bb.YLength, slot.cavity_width - 2 * Hardware.SIDE_CLEARANCE, delta=TOL)
                    # Through hole on the axis.
                    self.assertFalse(nut.isInside(FreeCAD.Vector(0, 0, -slot.lip - 0.5), TOL, True))

    def test_threads(self):
        expected = {("B-Type", "2020"): "M4", ("B-Type", "3030"): "M6", ("B-Type", "4040"): "M8",
                    ("Generic", "2020"): "M4", ("Generic", "4040"): "M6"}
        for (family, size), thread in expected.items():
            with self.subTest(family=family, size=size):
                self.assertEqual(Hardware.thread_for_slot(Profiles.get_profile(family, size).slot), thread)

    def test_hole_too_big(self):
        with self.assertRaises(Profiles.ProfileError):
            Hardware.make_nut_shape(Profiles.get_profile("B-Type", "2020").slot, "M8")


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class HardwareTestCase(unittest.TestCase):

    def setUp(self):
        self.doc = FreeCAD.newDocument("TSlotHardwareTest")
        self.base = self.extrusion("4040", 500, FreeCAD.Placement(
            FreeCAD.Vector(0, 0, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)))

    def tearDown(self):
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)

    def extrusion(self, size, length, placement, family="B-Type"):
        obj = Extrusion.make_extrusion(self.doc, size=size, length=length, family=family)
        obj.Placement = placement
        self.doc.recompute()
        return obj

    def post(self, x=20.0, size="4040", family="B-Type"):
        return self.extrusion(size, 500, FreeCAD.Placement(FreeCAD.Vector(x, 0, 20), FreeCAD.Rotation()), family)

    def assertClean(self, obj):
        self.assertTrue(obj.isValid(), obj.getStatusString())
        self.assertFalse({"Touched", "Invalid", "Error"} & set(obj.State), (obj.Label, obj.State))

    def assertNoClash(self, a, b, limit=TOL):
        self.assertLess(a.Shape.common(b.Shape).Volume, limit, f"{a.Label} cuts into {b.Label}")


class TestNuts(HardwareTestCase):

    def test_manual_nut_in_slot(self):
        nut = Hardware.make_nut(self.doc, self.base, "-X", 0, 120.0)
        self.doc.recompute()
        self.assertClean(nut)
        self.assertEqual(nut.Thread, "M8")
        self.assertEqual(nut.Label, "T-nut M8")
        self.assertNoClash(nut, self.base)
        self.assertLess(nut.Shape.distToShape(self.base.Shape)[0], 1e-6)  # bears on the lips
        # On the top face (Z = 20), at X = 120, centred on Y = 0.
        c = nut.Shape.BoundBox.Center
        self.assertAlmostEqual(c.x, 120.0, delta=TOL)
        self.assertAlmostEqual(c.y, 0.0, delta=TOL)
        self.assertLess(nut.Shape.BoundBox.ZMax, 20.0)

    def test_locate_snaps_to_nearest_slot(self):
        point = FreeCAD.Vector(200.0, 3.0, 20.0)
        side, slot, position, offset = Hardware.locate_in_slot(self.base, point, FreeCAD.Vector(0, 0, 1), snap=True)
        self.assertEqual((side, slot), ("-X", 0))
        self.assertAlmostEqual(position, 200.0, delta=TOL)
        self.assertAlmostEqual(abs(offset), 3.0, delta=TOL)
        with self.assertRaises(Profiles.ProfileError):
            Hardware.locate_in_slot(self.base, point, FreeCAD.Vector(0, 0, 1))
        with self.assertRaises(Profiles.ProfileError):  # not on a face
            Hardware.locate_in_slot(self.base, FreeCAD.Vector(200, 0, 25), FreeCAD.Vector(0, 0, 1), snap=True)

    def test_nut_follows_profile(self):
        nut = Hardware.make_nut(self.doc, self.base, "-X", 0, 120.0)
        self.doc.recompute()
        self.base.Placement.Base = FreeCAD.Vector(0, 50, 0)
        self.doc.recompute()
        self.assertAlmostEqual(nut.Shape.BoundBox.Center.y, 50.0, delta=TOL)
        self.assertNoClash(nut, self.base)

    def test_bracket_nuts(self):
        post = self.post()
        (bracket,) = CornerBracket.make_corner_brackets(self.doc, self.base, post)
        nuts = [Hardware.make_bracket_nut(self.doc, bracket, leg) for leg in ("Base", "Post")]
        self.doc.recompute()
        b = Brackets.get_bracket("40")
        mid = (b.hole_start + b.hole_end) / 2.0
        base_nut, post_nut = nuts
        for nut in nuts:
            self.assertClean(nut)
            self.assertEqual(nut.Thread, "M8")
            for other in (self.base, post, bracket):
                self.assertNoClash(nut, other)
        self.assertEqual(base_nut.Profile, self.base)
        self.assertAlmostEqual(base_nut.Position.Value, 40.0 + mid, delta=TOL)
        self.assertEqual(post_nut.Profile, post)
        self.assertEqual(post_nut.Side, "+X")
        self.assertAlmostEqual(post_nut.Position.Value, mid, delta=TOL)
        self.assertEqual(CornerBracket.nuts_of(bracket), nuts)

        # The bracket slides along the base with the post; so does the base nut.
        post.Placement.Base = FreeCAD.Vector(120, 0, 20)
        self.doc.recompute()
        self.assertAlmostEqual(base_nut.Position.Value, 140.0 + mid, delta=TOL)
        for nut in nuts:
            self.assertClean(nut)
            self.assertNoClash(nut, self.base)

    def test_bracket_nut_thread_fits_generic_slot(self):
        """A 40 bracket wants M8, but a Generic 4040's 8 mm slot only takes M6."""
        base = self.extrusion("4040", 500, FreeCAD.Placement(
            FreeCAD.Vector(0, 200, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)), "Generic")
        post = self.extrusion("4040", 300, FreeCAD.Placement(FreeCAD.Vector(20, 200, 20), FreeCAD.Rotation()), "Generic")
        (bracket,) = CornerBracket.make_corner_brackets(self.doc, base, post)
        nut = Hardware.make_bracket_nut(self.doc, bracket, "Base")
        self.doc.recompute()
        self.assertEqual(nut.Thread, "M6")
        self.assertClean(nut)
        self.assertNoClash(nut, base)

    def test_save_reopen(self):
        nut = Hardware.make_nut(self.doc, self.base, "-X", 0, 120.0)
        self.doc.recompute()
        name = nut.Name
        tmp = tempfile.mkdtemp(prefix="tslot-test-")
        try:
            path = os.path.join(tmp, "nut.FCStd")
            self.doc.saveAs(path)
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = FreeCAD.openDocument(path)
            nut = self.doc.getObject(name)
            self.assertIsInstance(nut.Proxy, Hardware.TSlotNut)
            nut.Position = 300
            self.doc.recompute()
            self.assertAlmostEqual(nut.Shape.BoundBox.Center.x, 300.0, delta=TOL)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(HAVE_FASTENERS, "the Fasteners workbench is not installed")
class TestScrews(HardwareTestCase):

    def joint(self, size="4040", family="B-Type"):
        post = self.post(size=size, family=family)
        (bracket,) = CornerBracket.make_corner_brackets(self.doc, self.base, post, hardware=True)
        self.doc.recompute()
        nuts = CornerBracket.nuts_of(bracket)
        screws = [s for n in nuts for s in Hardware.screws_of(n)]
        return post, bracket, nuts, screws

    def test_bracket_hardware(self):
        post, bracket, nuts, screws = self.joint()
        self.assertEqual(len(nuts), 2)
        self.assertEqual(len(screws), 2)
        for screw in screws:
            self.assertClean(screw)
            self.assertEqual(screw.Type, Hardware.BRACKET_SCREW)
            self.assertEqual(screw.Diameter, "M8")
            self.assertEqual(screw.Length, "16")
            self.assertAlmostEqual(screw.AttachmentOffset.Base.z, Brackets.get_bracket("40").wall)
            for other in [self.base, post, bracket] + nuts:
                self.assertNoClash(screw, other, OVERLAP)
        a, b = screws
        self.assertNoClash(a, b, OVERLAP)

    def test_smaller_joints(self):
        for size, thread in (("2020", "M4"), ("3030", "M6")):
            with self.subTest(size=size):
                base = self.extrusion(size, 400, FreeCAD.Placement(
                    FreeCAD.Vector(0, 300, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)))
                half = float(size[:2]) / 2.0
                post = self.extrusion(size, 300, FreeCAD.Placement(FreeCAD.Vector(half, 300, half), FreeCAD.Rotation()))
                (bracket,) = CornerBracket.make_corner_brackets(self.doc, base, post, hardware=True)
                self.doc.recompute()
                nuts = CornerBracket.nuts_of(bracket)
                screws = [s for n in nuts for s in Hardware.screws_of(n)]
                self.assertEqual((len(nuts), len(screws)), (2, 2))
                for screw in screws:
                    self.assertClean(screw)
                    self.assertEqual(screw.Diameter, thread)
                    for other in [base, post, bracket] + nuts:
                        self.assertNoClash(screw, other, OVERLAP)
                for obj in [bracket] + nuts + screws:
                    self.doc.removeObject(obj.Name)
                for obj in (base, post):
                    self.doc.removeObject(obj.Name)

    def test_screws_follow_the_bracket(self):
        post, bracket, nuts, screws = self.joint()
        before = [s.Placement.Base for s in screws]
        post.Placement.Base = FreeCAD.Vector(120, 0, 20)
        self.doc.recompute()
        for b, screw in zip(before, screws):
            self.assertAlmostEqual((screw.Placement.Base - b).x, 100.0, delta=TOL)
            self.assertClean(screw)
            self.assertNoClash(screw, self.base, OVERLAP)

    def test_manual_screw(self):
        nut = Hardware.make_nut(self.doc, self.base, "-X", 0, 120.0)
        screw = Hardware.make_screw(self.doc, nut)
        self.doc.recompute()
        self.assertClean(screw)
        self.assertEqual(screw.Type, Hardware.MANUAL_SCREW)
        self.assertEqual(Hardware.screws_of(nut), [screw])
        # Longest standard M8 that stays off the slot floor: depth 12.5 - 0.5 -> 12.
        self.assertEqual(screw.Length, "12")
        self.assertNoClash(screw, self.base, OVERLAP)
        self.assertNoClash(screw, nut, OVERLAP)

    def test_save_reopen_follows(self):
        post, bracket, nuts, screws = self.joint()
        names = [s.Name for s in screws]
        tmp = tempfile.mkdtemp(prefix="tslot-test-")
        try:
            path = os.path.join(tmp, "hardware.FCStd")
            self.doc.saveAs(path)
            post_name = post.Name
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = FreeCAD.openDocument(path)
            before = [self.doc.getObject(n).Placement.Base for n in names]
            self.doc.getObject(post_name).Placement.Base = FreeCAD.Vector(70, 0, 20)
            self.doc.recompute()
            for n, b in zip(names, before):
                self.assertAlmostEqual((self.doc.getObject(n).Placement.Base - b).x, 50.0, delta=TOL)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
