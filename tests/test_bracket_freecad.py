# SPDX-License-Identifier: LGPL-2.1-or-later
"""Corner bracket tests that need a real FreeCAD (run with tools/run_tests.sh).

The joints are built in world coordinates. The base is a 4040 lying along
+X from X = 0 to 500, centred on the X axis, so its top face is Z = 20.
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
    from freecad.TSlotWorkbench import Brackets, CornerBracket, Extrusion

TOL = 1e-6


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class TestBracketShape(unittest.TestCase):

    def test_valid_single_solid(self):
        for size in Brackets.sizes():
            with self.subTest(size=size):
                b = Brackets.get_bracket(size)
                shape = CornerBracket.make_bracket_shape(b)
                self.assertTrue(shape.isValid())
                self.assertEqual(len(Part.Shape(shape).Solids), 1)
                shape.check(True)
                bb = shape.BoundBox
                self.assertAlmostEqual(bb.XMin, -b.width / 2.0, delta=TOL)
                self.assertAlmostEqual(bb.XMax, b.width / 2.0, delta=TOL)
                self.assertAlmostEqual(bb.YMin, 0.0, delta=TOL)
                self.assertAlmostEqual(bb.YMax, b.leg, delta=TOL)
                self.assertAlmostEqual(bb.ZMin, 0.0, delta=TOL)
                self.assertAlmostEqual(bb.ZMax, b.leg, delta=TOL)

    def test_bolt_slots_go_through_both_legs(self):
        for size in Brackets.sizes():
            with self.subTest(size=size):
                b = Brackets.get_bracket(size)
                shape = CornerBracket.make_bracket_shape(b)
                mid = (b.hole_start + b.hole_end) / 2.0
                v = FreeCAD.Vector
                self.assertFalse(shape.isInside(v(0, mid, b.wall / 2.0), TOL, True))
                self.assertFalse(shape.isInside(v(0, b.wall / 2.0, mid), TOL, True))
                # Solid beside the slot, and in the cheeks.
                self.assertTrue(shape.isInside(v(b.hole_width / 2.0 + 0.5, mid, b.wall / 2.0), TOL, True))
                self.assertTrue(shape.isInside(v(b.width / 2.0 - b.wall / 2.0, b.leg / 4.0, b.leg / 4.0), TOL, True))
                # Open between the cheeks, under the hypotenuse.
                self.assertFalse(shape.isInside(v(0, b.leg / 3.0, b.leg / 3.0), TOL, True))


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class TestCornerBrackets(unittest.TestCase):

    def setUp(self):
        self.doc = FreeCAD.newDocument("TSlotBracketTest")
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

    def post(self, x, size="4040", length=500, y=0.0):
        """A vertical post standing on the base's top face, centred at (x, y)."""
        return self.extrusion(size, length, FreeCAD.Placement(FreeCAD.Vector(x, y, 20), FreeCAD.Rotation()))

    def brackets(self, a, b, faces=()):
        objs = CornerBracket.make_corner_brackets(self.doc, a, b, faces)
        self.doc.recompute()
        for obj in objs:
            self.assertTrue(obj.isValid(), obj.getStatusString())
            self.assertFalse({"Touched", "Invalid", "Error"} & set(obj.State), obj.State)
        return objs

    def assertSeated(self, bracket, *profiles):
        """Touches each profile without cutting into it."""
        for p in profiles:
            self.assertLess(bracket.Shape.common(p.Shape).Volume, 1e-6, p.Label)
            self.assertLess(bracket.Shape.distToShape(p.Shape)[0], 1e-6, p.Label)

    def test_l_corner_gets_one_bracket(self):
        post = self.post(20.0)  # flush with the base's end
        (bracket,) = self.brackets(self.base, post)
        self.assertEqual((bracket.Post, bracket.Base), (post, self.base))
        self.assertEqual((bracket.PostEnd, bracket.PostSide, bracket.Slot), ("Start", "+X", 0))
        self.assertEqual(bracket.BracketSize, "40")
        self.assertEqual(bracket.Label, "40 corner bracket")
        bb = bracket.Shape.BoundBox
        b = Brackets.get_bracket("40")
        self.assertAlmostEqual(bb.XMin, 40.0, delta=TOL)
        self.assertAlmostEqual(bb.XMax, 40.0 + b.leg, delta=TOL)
        self.assertAlmostEqual(bb.YMin, -b.width / 2.0, delta=TOL)
        self.assertAlmostEqual(bb.ZMin, 20.0, delta=TOL)
        self.assertAlmostEqual(bb.ZMax, 20.0 + b.leg, delta=TOL)
        self.assertSeated(bracket, self.base, post)

    def test_t_joint_gets_two_brackets(self):
        post = self.post(250.0)
        brackets = self.brackets(post, self.base)
        self.assertEqual(sorted(b.PostSide for b in brackets), ["+X", "-X"])
        for bracket in brackets:
            self.assertSeated(bracket, self.base, post)

    def test_selected_face_picks_one_corner(self):
        post = self.post(250.0)
        face = next(f for f in post.Shape.Faces
                    if isinstance(f.Surface, Part.Plane)
                    and f.normalAt(0, 0).sub(FreeCAD.Vector(-1, 0, 0)).Length < 1e-6
                    and abs(f.Vertexes[0].Point.x - 230.0) < 1e-6)
        (bracket,) = self.brackets(post, self.base, [(post, face)])
        self.assertEqual(bracket.PostSide, "-X")
        self.assertLess(bracket.Shape.BoundBox.XMax, 230.0 + TOL)

    def test_unrelated_face_gives_nothing(self):
        post = self.post(250.0)
        top = next(f for f in post.Shape.Faces if f.normalAt(0, 0).z > 0.5)
        self.assertEqual(self.brackets(post, self.base, [(post, top)]), [])

    def test_no_corner_when_apart_or_parallel(self):
        floating = self.extrusion("4040", 500, FreeCAD.Placement(FreeCAD.Vector(250, 0, 30), FreeCAD.Rotation()))
        self.assertEqual(CornerBracket.find_corners(self.base, floating), [])
        parallel = self.extrusion("4040", 500, FreeCAD.Placement(
            FreeCAD.Vector(0, 40, 0), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90)))
        self.assertEqual(CornerBracket.find_corners(self.base, parallel), [])

    def test_explains_stale_face_selection(self):
        post = self.post(250.0)
        top = next(f for f in post.Shape.Faces if f.normalAt(0, 0).z > 0.5)
        message = CornerBracket.explain_no_corner(post, self.base, [(post, top)])
        self.assertIn("2 inside corner(s) found", message)
        self.assertIn("select just the two extrusions", message)

    def test_explains_near_misses(self):
        cases = (
            (FreeCAD.Placement(FreeCAD.Vector(250, 0, 20.5), FreeCAD.Rotation()), "0.500 mm gap"),
            (FreeCAD.Placement(FreeCAD.Vector(250, 0, 19.75), FreeCAD.Rotation()), "0.250 mm into the face"),
            (FreeCAD.Placement(FreeCAD.Vector(250, 0, 20), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 1.5)),
             "tilted 1.50 degrees"),
        )
        for placement, expected in cases:
            with self.subTest(expected=expected):
                post = self.extrusion("4040", 500, placement)
                self.assertEqual(CornerBracket.find_corners(post, self.base), [])
                message = CornerBracket.explain_no_corner(post, self.base)
                self.assertIn(expected, message)
                self.assertIn(f"the start of {post.Label}", message)
                self.assertIn(f"-X face of {self.base.Label}", message)  # the base's top face
                self.doc.removeObject(post.Name)

    def assertSnapped(self, post, x=250.0):
        """The post stands exactly on the base's top face, square to it, at ``x``."""
        pl = post.Placement
        self.assertAlmostEqual(pl.Base.x, x, delta=1e-6)
        self.assertAlmostEqual(pl.Base.y, 0.0, delta=1e-6)
        self.assertAlmostEqual(pl.Base.z, 20.0, delta=1e-6)
        self.assertLess(pl.Rotation.multVec(FreeCAD.Vector(0, 0, 1)).sub(FreeCAD.Vector(0, 0, 1)).Length, 1e-9)
        self.assertLess(pl.Rotation.multVec(FreeCAD.Vector(1, 0, 0)).sub(FreeCAD.Vector(1, 0, 0)).Length, 1e-9)

    def test_snaps_near_misses(self):
        cases = (
            ("gap", FreeCAD.Placement(FreeCAD.Vector(250, 0, 24), FreeCAD.Rotation()), "closed a 4.000 mm gap"),
            ("overlap", FreeCAD.Placement(FreeCAD.Vector(250, 0, 18), FreeCAD.Rotation()),
             "pulled it 2.000 mm out of the face"),
            ("tilt", FreeCAD.Placement(FreeCAD.Vector(250, 0, 20), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 2)),
             "straightened a 2.00 degree tilt"),
            ("twist", FreeCAD.Placement(FreeCAD.Vector(250, 0, 21), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), -3)),
             "turned it 3.00 degrees"),
        )
        for name, placement, expected in cases:
            with self.subTest(name):
                post = self.extrusion("4040", 500, placement)
                message = CornerBracket.snap_joint(self.base, post)
                self.assertIn(f"Snapped {post.Label} onto {self.base.Label}", message)
                self.assertIn(expected, message)
                self.doc.recompute()
                self.assertSnapped(post)
                brackets = self.brackets(self.base, post)
                self.assertEqual(len(brackets), 2)
                for bracket in brackets:
                    self.assertSeated(bracket, self.base, post)
                    self.doc.removeObject(bracket.Name)
                self.doc.removeObject(post.Name)

    def test_snaps_tilt_about_end_centre(self):
        """A tilted post pivots about the centre of its end, so that point stays put."""
        post = self.extrusion("4040", 500, FreeCAD.Placement(
            FreeCAD.Vector(100, 0, 23), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 4)))
        CornerBracket.snap_joint(self.base, post)
        self.doc.recompute()
        self.assertSnapped(post, x=100.0)

    def test_does_not_snap_far_misses(self):
        for placement in (
            FreeCAD.Placement(FreeCAD.Vector(250, 0, 35), FreeCAD.Rotation()),        # 15 mm gap
            FreeCAD.Placement(FreeCAD.Vector(250, 0, 20), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 20)),
            FreeCAD.Placement(FreeCAD.Vector(250, 0, 20), FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 30)),
        ):
            with self.subTest(placement=placement):
                post = self.extrusion("4040", 500, placement)
                self.assertIsNone(CornerBracket.snap_joint(self.base, post))
                self.assertEqual(post.Placement, placement)
                self.assertIn("too far off to snap", CornerBracket.explain_no_corner(self.base, post))
                self.doc.removeObject(post.Name)

    def test_exact_joint_is_not_moved(self):
        post = self.post(250.0)
        self.assertIsNone(CornerBracket.snap_joint(self.base, post))

    def test_smaller_post_gets_smaller_bracket(self):
        post = self.post(250.0, size="2020")
        brackets = self.brackets(post, self.base)
        # Only along the base: across its 40 mm face, an 18 mm leg from the
        # 2020's side would overhang the edge.
        self.assertEqual(sorted(b.PostSide for b in brackets), ["+X", "-X"])
        for bracket in brackets:
            self.assertEqual(bracket.BracketSize, "20")
            self.assertSeated(bracket, self.base, post)

    def test_one_bracket_per_slot(self):
        # A 2040 post: two slots on each wide side (its local ±X faces are 40 long, in Y)
        post = self.post(250.0, size="2040")
        brackets = self.brackets(post, self.base)
        wide = [b for b in brackets if b.PostSide in ("+X", "-X")]
        self.assertEqual(sorted((b.PostSide, b.Slot) for b in wide), [("+X", 0), ("+X", 1), ("-X", 0), ("-X", 1)])
        for bracket in brackets:
            self.assertSeated(bracket, self.base, post)

    def test_follows_post(self):
        post = self.post(250.0)
        (bracket, _) = self.brackets(post, self.base)
        before = bracket.Shape.BoundBox
        post.Placement.Base = FreeCAD.Vector(300.0, 0, 20)
        self.doc.recompute()
        after = bracket.Shape.BoundBox
        self.assertAlmostEqual(after.XMin - before.XMin, 50.0, delta=TOL)
        self.assertSeated(bracket, self.base, post)

    def test_follows_post_end(self):
        """A post hanging down onto the base meets it with its End; the bracket follows its length."""
        post = self.extrusion("4040", 500, FreeCAD.Placement(
            FreeCAD.Vector(250, 0, 520), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180)))
        brackets = self.brackets(post, self.base)
        self.assertEqual(len(brackets), 2)
        self.assertEqual({b.PostEnd for b in brackets}, {"End"})
        for bracket in brackets:
            self.assertSeated(bracket, self.base, post)

        post.Length = 400  # now ends 100 mm above the base
        self.doc.recompute()
        for bracket in brackets:
            self.assertAlmostEqual(bracket.Shape.BoundBox.ZMin, 120.0, delta=TOL)
            self.assertLess(bracket.Shape.distToShape(post.Shape)[0], 1e-6)
            self.assertFalse(CornerBracket.bracket_fits(
                CornerBracket.Corner(post, self.base, "End", bracket.PostSide, bracket.Slot),
                Brackets.get_bracket("40")))

    def test_bracket_size_editable(self):
        post = self.post(20.0)
        (bracket,) = self.brackets(self.base, post)
        bracket.BracketSize = "30"
        self.doc.recompute()
        self.assertAlmostEqual(bracket.Shape.BoundBox.ZLength, Brackets.get_bracket("30").leg, delta=TOL)
        self.assertSeated(bracket, self.base, post)

    def test_undo(self):
        post = self.post(20.0)
        self.doc.UndoMode = 1
        self.doc.openTransaction("Corner Bracket")
        self.brackets(self.base, post)
        self.doc.commitTransaction()
        self.assertEqual(len(self.doc.Objects), 3)
        self.doc.undo()
        self.assertEqual(len(self.doc.Objects), 2)

    def test_save_reopen(self):
        post = self.post(20.0)
        (bracket,) = self.brackets(self.base, post)
        name, post_name, box = bracket.Name, post.Name, bracket.Shape.BoundBox
        tmp = tempfile.mkdtemp(prefix="tslot-test-")
        try:
            path = os.path.join(tmp, "bracket.FCStd")
            self.doc.saveAs(path)
            FreeCAD.closeDocument(self.doc.Name)
            self.doc = FreeCAD.openDocument(path)
            bracket = self.doc.getObject(name)
            self.assertIsInstance(bracket.Proxy, CornerBracket.CornerBracket)
            self.assertEqual(bracket.Post.Name, post_name)
            self.assertIn("ReadOnly", bracket.getEditorMode("Placement"))
            bracket.Post.Placement.Base = FreeCAD.Vector(60, 0, 20)
            self.doc.recompute()
            self.assertAlmostEqual(bracket.Shape.BoundBox.XMin, box.XMin + 40.0, delta=TOL)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
