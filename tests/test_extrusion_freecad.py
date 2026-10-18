# SPDX-License-Identifier: LGPL-2.1-or-later
"""Integration tests that need a real FreeCAD (run with tools/run_tests.sh).

Under plain Python these are skipped, not faked.
"""

import math
import os
import shutil
import tempfile
import unittest

try:
    import FreeCAD
    import Part  # noqa: F401
except ImportError:
    FreeCAD = None

if FreeCAD is not None:
    import freecad.TSlotWorkbench
    from freecad.TSlotWorkbench import Extrusion, Profiles

_MOD_DIR = os.path.join(FreeCAD.getUserAppDataDir(), "Mod") if FreeCAD else ""
_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def expected_area(size):
    """Section area worked out by hand: square minus four slots minus the bore."""
    p = Profiles.get_profile("Generic", size)
    s = p.slot
    slot = (s.opening * s.lip + s.cavity_width * s.cavity_height
            + (s.cavity_width + s.floor_width) / 2.0 * (s.depth - s.taper_start))
    return p.outer ** 2 - 4.0 * slot - math.pi * (p.bore_diameter / 2.0) ** 2


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class FreeCADTestCase(unittest.TestCase):

    def setUp(self):
        self.doc = FreeCAD.newDocument("TSlotTest")
        self.tmpdir = tempfile.mkdtemp(prefix="tslot-test-")

    def tearDown(self):
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def make(self, **kwargs):
        obj = Extrusion.make_extrusion(self.doc, **kwargs)
        self.doc.recompute()
        return obj

    def assertClean(self, obj):
        """Recomputed without error and not waiting for another recompute."""
        self.assertFalse({"Touched", "Invalid", "Error"} & set(obj.State), obj.State)

    def assertProfile(self, obj, size, length):
        """Valid single solid with the profile's outer size, length and section area."""
        edge = float(size[:2])
        self.assertBox(obj, edge, edge, length)
        self.assertAlmostEqual(obj.Shape.Volume, expected_area(size) * length, delta=1e-6 * length)

    def assertBox(self, obj, x, y, z):
        self.assertFalse(obj.Shape.isNull())
        self.assertTrue(obj.Shape.isValid())
        self.assertEqual(len(obj.Shape.Solids), 1)
        bb = obj.Shape.BoundBox
        self.assertAlmostEqual(bb.XLength, x, delta=1e-6)
        self.assertAlmostEqual(bb.YLength, y, delta=1e-6)
        self.assertAlmostEqual(bb.ZLength, z, delta=1e-6)
        self.assertGreater(obj.Shape.Volume, 0.0)


class TestAddonDiscovery(FreeCADTestCase):

    def test_loaded_from_user_mod_dir(self):
        """FreeCAD found the addon through its Mod directory, not sys.path tricks."""
        path = os.path.abspath(freecad.TSlotWorkbench.__file__)
        self.assertTrue(path.startswith(os.path.abspath(_MOD_DIR)), path)

    def test_icons_exist(self):
        for name in ("Logo.svg", "CreateExtrusion.svg"):
            self.assertTrue(os.path.isfile(freecad.TSlotWorkbench.icon_path(name)), name)


class TestExtrusionObject(FreeCADTestCase):

    def test_default_object(self):
        obj = self.make()
        self.assertEqual(obj.TypeId, "Part::FeaturePython")
        self.assertIsInstance(obj.Proxy, Extrusion.Extrusion)
        self.assertEqual(obj.ProfileFamily, "Generic")
        self.assertEqual(obj.ProfileSize, "4040")
        self.assertEqual(obj.getEnumerationsOfProperty("ProfileSize"), ["2020", "3030", "4040"])
        self.assertAlmostEqual(obj.Length.Value, 750.0)
        self.assertProfile(obj, "4040", 750)
        self.assertAlmostEqual(obj.CrossSectionArea.Value, expected_area("4040"), places=6)
        self.assertEqual(obj.SchemaVersion, Extrusion.SCHEMA_VERSION)
        self.assertEqual(obj.Label, "Extrusion 4040 x 750 mm")
        self.assertClean(obj)

    def test_section_is_centred_on_z_axis(self):
        bb = self.make().Shape.BoundBox
        self.assertAlmostEqual(bb.XMin, -20.0)
        self.assertAlmostEqual(bb.YMax, 20.0)
        self.assertAlmostEqual(bb.ZMin, 0.0)

    def test_each_size_and_length(self):
        for size, edge in (("2020", 20), ("3030", 30), ("4040", 40)):
            for length in (1.5, 750, 2000):
                with self.subTest(size=size, length=length):
                    obj = self.make(size=size, length=length)
                    self.assertProfile(obj, size, length)
                    self.assertAlmostEqual(obj.CrossSectionArea.Value, expected_area(size), places=6)

    def test_update_and_recompute(self):
        obj = self.make()
        obj.ProfileSize = "3030"
        obj.Length = 1200
        self.assertIn("Touched", obj.State)
        self.doc.recompute()
        self.assertProfile(obj, "3030", 1200)
        self.assertAlmostEqual(obj.CrossSectionArea.Value, expected_area("3030"), places=6)
        self.assertEqual(obj.Label, "Extrusion 3030 x 1200 mm")
        self.assertClean(obj)

    def test_placement_preserved(self):
        obj = self.make()
        placement = FreeCAD.Placement(FreeCAD.Vector(100, 200, 300), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
        obj.Placement = placement
        obj.Length = 500
        self.doc.recompute()
        self.assertTrue(obj.Placement.isSame(placement, 1e-9))
        bb = obj.Shape.BoundBox
        # Rotated 90 degrees about X: local Z maps to global -Y.
        self.assertAlmostEqual(bb.YLength, 500.0)
        self.assertAlmostEqual(bb.YMax, 200.0)
        self.assertAlmostEqual(bb.XMin, 80.0)

    def test_custom_label_not_overwritten(self):
        obj = self.make()
        obj.Label = "Left upright"
        obj.ProfileSize = "2020"
        self.doc.recompute()
        self.assertEqual(obj.Label, "Left upright")
        self.assertProfile(obj, "2020", 750)

    def test_duplicate_auto_labels_keep_updating(self):
        self.make()
        second = self.make()
        self.assertTrue(second.Label.startswith("Extrusion 4040 x 750 mm"))
        second.Length = 600
        self.doc.recompute()
        self.assertEqual(second.Label, "Extrusion 4040 x 600 mm")

    def test_cross_section_area_is_read_only(self):
        obj = self.make()
        self.assertIn("ReadOnly", obj.getEditorMode("CrossSectionArea"))
        self.assertIn("Hidden", obj.getEditorMode("AutoLabel"))

    def test_zero_length_marks_error(self):
        obj = self.make()
        obj.Length = 0
        self.doc.recompute()
        self.assertIn("Invalid", obj.State)
        obj.Length = 10
        self.doc.recompute()
        self.assertTrue(obj.isValid())
        self.assertProfile(obj, "4040", 10)

    def test_factory_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            Extrusion.make_extrusion(self.doc, size="9090")
        with self.assertRaises(ValueError):
            Extrusion.make_extrusion(self.doc, length=-5)
        self.assertEqual(self.doc.Objects, [])

    def test_undo_removes_object(self):
        self.doc.UndoMode = 1
        self.doc.openTransaction("Create Extrusion")
        self.make()
        self.doc.commitTransaction()
        self.assertEqual(len(self.doc.Objects), 1)
        self.doc.undo()
        self.assertEqual(len(self.doc.Objects), 0)


class TestPersistence(FreeCADTestCase):

    def save_and_reopen(self):
        path = os.path.join(self.tmpdir, "extrusion.FCStd")
        self.doc.saveAs(path)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = FreeCAD.openDocument(path)
        return self.doc

    def test_save_reopen_and_edit(self):
        obj = self.make()
        obj.ProfileSize = "3030"
        obj.Length = 1200
        obj.Placement.Base = FreeCAD.Vector(10, 20, 30)
        self.doc.recompute()
        name = obj.Name

        doc = self.save_and_reopen()
        obj = doc.getObject(name)
        self.assertIsInstance(obj.Proxy, Extrusion.Extrusion)
        self.assertEqual(obj.ProfileSize, "3030")
        self.assertAlmostEqual(obj.Length.Value, 1200.0)
        self.assertEqual(obj.getEnumerationsOfProperty("ProfileSize"), ["2020", "3030", "4040"])
        self.assertIn("ReadOnly", obj.getEditorMode("CrossSectionArea"))
        self.assertProfile(obj, "3030", 1200)
        self.assertEqual(obj.Placement.Base, FreeCAD.Vector(10, 20, 30))

        obj.ProfileSize = "2020"
        obj.Length = 300
        doc.recompute()
        self.assertClean(obj)
        self.assertProfile(obj, "2020", 300)
        self.assertEqual(obj.Label, "Extrusion 2020 x 300 mm")
        self.assertEqual(obj.Placement.Base, FreeCAD.Vector(10, 20, 30))

    def test_custom_label_survives_reopen(self):
        obj = self.make()
        obj.Label = "Crossbar"
        name = obj.Name
        doc = self.save_and_reopen()
        obj = doc.getObject(name)
        obj.Length = 400
        doc.recompute()
        self.assertEqual(obj.Label, "Crossbar")
        self.assertProfile(obj, "4040", 400)

    def test_stale_size_choices_refreshed_on_restore(self):
        """A document saved with fewer sizes gains the current catalogue's sizes."""
        obj = self.make(size="2020")
        obj.ProfileSize = ["2020"]
        name = obj.Name
        doc = self.save_and_reopen()
        obj = doc.getObject(name)
        self.assertEqual(obj.getEnumerationsOfProperty("ProfileSize"), ["2020", "3030", "4040"])
        self.assertEqual(obj.ProfileSize, "2020")


class TestMvpDocumentMigration(FreeCADTestCase):
    """tests/fixtures/mvp_v0_1.FCStd was saved by v0.1 (rectangular boxes).

    It holds "Extrusion" (4040 x 750, automatic label) and "Extrusion001"
    (2020 x 300, label "Custom label", moved and rotated).
    """

    def open_fixture(self):
        path = os.path.join(self.tmpdir, "mvp.FCStd")
        shutil.copy(os.path.join(_FIXTURES, "mvp_v0_1.FCStd"), path)
        FreeCAD.closeDocument(self.doc.Name)
        self.doc = FreeCAD.openDocument(path)
        return self.doc

    def test_raw_fixture_holds_boxes(self):
        """The stored v0.1 shapes are plain blocks (read without opening the document)."""
        import zipfile

        with zipfile.ZipFile(os.path.join(_FIXTURES, "mvp_v0_1.FCStd")) as archive:
            brep = archive.read("Extrusion.Shape.brp").decode()
        stored = Part.Shape()
        stored.importBrepFromString(brep)
        self.assertAlmostEqual(stored.Volume, 40 * 40 * 750, delta=1e-3)

    def test_upgraded_on_open(self):
        doc = self.open_fixture()
        auto, custom = doc.getObject("Extrusion"), doc.getObject("Extrusion001")
        for obj in (auto, custom):
            self.assertIsInstance(obj.Proxy, Extrusion.Extrusion)
            self.assertEqual(obj.SchemaVersion, Extrusion.SCHEMA_VERSION)
        self.assertEqual(custom.Placement.Base, FreeCAD.Vector(100, 0, 0))
        self.assertNotIn("envelope", auto.getDocumentationOfProperty("ProfileFamily"))
        placement = FreeCAD.Placement(custom.Placement)

        # T-slot geometry straight after opening, and after a recompute.
        for _ in range(2):
            self.assertEqual(len(doc.Objects), 2)
            self.assertProfile(auto, "4040", 750)
            doc.recompute()
        self.assertProfile(auto, "4040", 750)
        self.assertAlmostEqual(auto.CrossSectionArea.Value, expected_area("4040"), places=6)
        self.assertEqual(auto.Label, "Extrusion 4040 x 750 mm")
        self.assertAlmostEqual(custom.Shape.Volume, expected_area("2020") * 300, delta=1e-3)
        self.assertEqual(custom.Label, "Custom label")
        self.assertTrue(custom.Placement.isSame(placement, 1e-9))

    def test_upgraded_document_stays_parametric(self):
        doc = self.open_fixture()
        doc.recompute()
        obj = doc.getObject("Extrusion")
        obj.ProfileSize = "3030"
        obj.Length = 1200
        doc.recompute()
        self.assertClean(obj)
        self.assertProfile(obj, "3030", 1200)

        path = os.path.join(self.tmpdir, "upgraded.FCStd")
        doc.saveAs(path)
        FreeCAD.closeDocument(doc.Name)
        self.doc = doc = FreeCAD.openDocument(path)
        obj = doc.getObject("Extrusion")
        self.assertNotIn("Touched", obj.State)  # already upgraded, no forced rebuild
        self.assertProfile(obj, "3030", 1200)
        obj.Length = 100
        doc.recompute()
        self.assertProfile(obj, "3030", 100)


class TestRecomputeHygiene(FreeCADTestCase):

    def test_recompute_adds_no_objects(self):
        obj = self.make()
        for size, length in (("3030", 100), ("2020", 2000), ("4040", 750)):
            obj.ProfileSize = size
            obj.Length = length
            self.doc.recompute()
            self.assertEqual([o.Name for o in self.doc.Objects], [obj.Name])
            self.assertProfile(obj, size, length)


if __name__ == "__main__":
    unittest.main()
