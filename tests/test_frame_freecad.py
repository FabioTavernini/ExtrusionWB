# SPDX-License-Identifier: LGPL-2.1-or-later
"""Frame generator and joint fitting tests that need a real FreeCAD (run with tools/run_tests.sh)."""

import unittest

try:
    import FreeCAD
except ImportError:
    FreeCAD = None

if FreeCAD is not None:
    from freecad.TSlotWorkbench import Brackets, CornerBracket, Extrusion, Frame, Hardware, Profiles

TOL = 1e-6


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class FrameTestCase(unittest.TestCase):

    def setUp(self):
        self.doc = FreeCAD.newDocument("TSlotFrameTest")

    def tearDown(self):
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)

    def extrusions(self, group):
        return [o for o in group.Group if isinstance(getattr(o, "Proxy", None), Extrusion.Extrusion)]

    def brackets(self, group):
        return [o for o in group.Group if isinstance(getattr(o, "Proxy", None), CornerBracket.CornerBracket)]

    def assertAllClean(self):
        for obj in self.doc.Objects:
            self.assertTrue(obj.isValid(), f"{obj.Label}: {obj.getStatusString()}")


class TestRectangularFrame(FrameTestCase):

    def test_flat_frame_is_exact(self):
        group = Frame.make_rectangular_frame(self.doc, 800, 400, size="4040", hardware=False)
        self.doc.recompute()
        self.assertAllClean()
        members = self.extrusions(group)
        self.assertEqual(sorted(m.Length.Value for m in members), [320, 320, 800, 800])
        box = members[0].Shape.BoundBox
        for m in members[1:]:
            box.add(m.Shape.BoundBox)
        self.assertAlmostEqual(box.XLength, 800, delta=TOL)
        self.assertAlmostEqual(box.YLength, 400, delta=TOL)
        self.assertAlmostEqual(box.ZLength, 40, delta=TOL)
        # One bracket in each inside corner of the rectangle, none out of plane.
        self.assertEqual(len(self.brackets(group)), 4)
        # Every member touches its neighbours without cutting into them.
        for a in members:
            for b in members:
                if a is not b:
                    self.assertLess(a.Shape.common(b.Shape).Volume, 1e-3)

    def test_nothing_left_to_snap_or_fit(self):
        group = Frame.make_rectangular_frame(self.doc, 800, 400, hardware=False)
        self.doc.recompute()
        members = self.extrusions(group)
        with self.assertRaisesRegex(Profiles.ProfileError, "already fit"):
            Frame.fit_joints(members)

    def test_box_frame(self):
        group = Frame.make_rectangular_frame(self.doc, 600, 400, 300, hardware=False)
        self.doc.recompute()
        self.assertAllClean()
        members = self.extrusions(group)
        self.assertEqual(len(members), 12)
        self.assertEqual(sorted(m.Length.Value for m in members if m.Length.Value == 220), [220] * 4)
        box = members[0].Shape.BoundBox
        for m in members[1:]:
            box.add(m.Shape.BoundBox)
        self.assertAlmostEqual(box.ZLength, 300, delta=TOL)
        # Each leg is bracketed to the long and the short member of its corner, top and bottom.
        brackets = self.brackets(group)
        self.assertEqual(len(brackets), 24)  # 16 on the legs, 8 in the rectangles' corners
        for leg in (m for m in members if m.Length.Value == 220):
            bases = [b.Base for b in brackets if b.Post == leg]
            self.assertEqual(len(bases), 4)
            self.assertEqual(len(set(bases)), 4)
            self.assertEqual(sorted(round(b.Length.Value) for b in bases), [320, 320, 600, 600])

    def test_hardware_and_other_sizes(self):
        group = Frame.make_rectangular_frame(self.doc, 500, 300, size="2020", family="B-Type", brackets="All")
        self.doc.recompute()
        self.assertAllClean()
        self.assertTrue(self.brackets(group))
        self.assertTrue([o for o in self.doc.Objects if Hardware.is_nut(o)])

    def test_no_brackets(self):
        group = Frame.make_rectangular_frame(self.doc, 500, 300, brackets="None")
        self.assertEqual(self.brackets(group), [])

    def test_invalid_sizes(self):
        for args in ((60, 400), (800, 80), (0, 400)):
            with self.subTest(args=args), self.assertRaises(Profiles.ProfileError):
                Frame.make_rectangular_frame(self.doc, *args)
        with self.assertRaises(Profiles.ProfileError):
            Frame.make_rectangular_frame(self.doc, 800, 400, 60)
        with self.assertRaises(Profiles.ProfileError):
            Frame.make_rectangular_frame(self.doc, 800, 400, brackets="Some")


class TestFitJoints(FrameTestCase):

    def test_fits_a_closed_loop(self):
        """The failure that snapping cannot fix: a post 1 mm too short for both its bases."""
        group = Frame.make_rectangular_frame(self.doc, 800, 400, brackets="None", hardware=False)
        self.doc.recompute()
        members = self.extrusions(group)
        shorts = [m for m in members if m.Length.Value == 320]
        for m in shorts:
            m.Length = 318
        shorts[0].Placement.Base = shorts[0].Placement.Base + FreeCAD.Vector(0, 1, 0)
        self.doc.recompute()
        messages = Frame.fit_joints(members)
        self.doc.recompute()
        self.assertEqual(len(messages), 2)
        for m in shorts:
            self.assertAlmostEqual(m.Length.Value, 320, delta=1e-6)
        self.assertAlmostEqual(shorts[0].Placement.Base.y, 40, delta=1e-6)
        for obj in members:
            self.assertIn("4040", obj.Label)
        with self.assertRaisesRegex(Profiles.ProfileError, "already fit"):
            Frame.fit_joints(members)

    def test_brackets_follow_a_fitted_post(self):
        group = Frame.make_rectangular_frame(self.doc, 800, 400, hardware=True)
        self.doc.recompute()
        members = self.extrusions(group)
        post = next(m for m in members if m.Length.Value == 320)
        post.Length = 300
        self.doc.recompute()
        Frame.fit_joints(members)
        self.doc.recompute()
        self.assertAlmostEqual(post.Length.Value, 320, delta=1e-6)
        self.assertAllClean()
        for bracket in self.brackets(group):
            corner = CornerBracket.Corner(bracket.Post, bracket.Base, bracket.PostEnd, bracket.PostSide,
                                          bracket.Slot)
            self.assertTrue(CornerBracket.bracket_fits(corner, Brackets.get_bracket(bracket.BracketSize)))

    def test_snaps_a_post_near_the_end_of_its_base_flush(self):
        base = Extrusion.make_extrusion(self.doc, length=500)
        base.Placement = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90))
        cases = (
            (60.0, 20.0),     # a full width (40 mm) in from the end: its side at 40, snaps flush
            (500 - 60.0, 480.0),
            (15.0, 20.0),     # overhanging the end by 5 mm
            (30.0, 20.0),     # inside the end by 10 mm
            (200.0, None),    # well inside: left alone
            (-20.0, None),    # only touching the end's edge: left alone
        )
        for x, expected in cases:
            with self.subTest(x=x):
                post = Extrusion.make_extrusion(self.doc, length=300)
                post.Placement = FreeCAD.Placement(FreeCAD.Vector(x, 0, 20), FreeCAD.Rotation())
                self.doc.recompute()
                if expected is None:
                    try:
                        Frame.fit_joints([base, post])
                    except Profiles.ProfileError:
                        pass
                    self.assertAlmostEqual(post.Placement.Base.x, x, delta=1e-6)
                else:
                    messages = Frame.fit_joints([base, post])
                    self.assertIn("flush", messages[0])
                    self.assertAlmostEqual(post.Placement.Base.x, expected, delta=1e-6)
                self.doc.removeObject(post.Name)

    def test_centres_a_post_that_is_a_little_off_its_base(self):
        base = Extrusion.make_extrusion(self.doc, length=500)
        base.Placement = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90))
        for y, expected in ((4.0, 0.0), (-7.5, 0.0), (17.7, 0.0), (-20.0, 0.0), (30.0, 30.0)):  # centre off the face: left alone
            with self.subTest(y=y):
                post = Extrusion.make_extrusion(self.doc, length=300)
                post.Placement = FreeCAD.Placement(FreeCAD.Vector(250, y, 20), FreeCAD.Rotation())
                self.doc.recompute()
                try:
                    messages = Frame.fit_joints([base, post])
                    self.assertIn("across", messages[0])
                except Profiles.ProfileError:
                    pass
                self.assertAlmostEqual(post.Placement.Base.y, expected, delta=1e-6)
                self.assertAlmostEqual(post.Placement.Base.x, 250.0, delta=1e-6)
                self.doc.removeObject(post.Name)

    def test_lines_a_narrow_post_up_with_the_nearer_side(self):
        base = Extrusion.make_extrusion(self.doc, length=500)  # 4040
        base.Placement = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90))
        for y, expected in ((2.0, 0.0), (7.0, 10.0), (-12.0, -10.0)):  # a 2020 post: centred, or flush with a side
            with self.subTest(y=y):
                post = Extrusion.make_extrusion(self.doc, size="2020", length=300)
                post.Placement = FreeCAD.Placement(FreeCAD.Vector(250, y, 20), FreeCAD.Rotation())
                self.doc.recompute()
                Frame.fit_joints([base, post])
                self.assertAlmostEqual(post.Placement.Base.y, expected, delta=1e-6)
                self.doc.removeObject(post.Name)

    def test_aligns_along_and_across_together_with_a_gap(self):
        base = Extrusion.make_extrusion(self.doc, length=500)
        base.Placement = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90))
        post = Extrusion.make_extrusion(self.doc, length=300)
        post.Placement = FreeCAD.Placement(FreeCAD.Vector(35, 3, 22), FreeCAD.Rotation())
        self.doc.recompute()
        Frame.fit_joints([base, post])
        self.doc.recompute()
        self.assertLess((post.Placement.Base - FreeCAD.Vector(20, 0, 20)).Length, 1e-6)

    def test_far_apart_extrusions_are_left_alone(self):
        a = Extrusion.make_extrusion(self.doc, length=500)
        b = Extrusion.make_extrusion(self.doc, length=500)
        b.Placement = FreeCAD.Placement(FreeCAD.Vector(1000, 0, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90))
        self.doc.recompute()
        with self.assertRaisesRegex(Profiles.ProfileError, "No joint to fit"):
            Frame.fit_joints([a, b])
