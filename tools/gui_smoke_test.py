# SPDX-License-Identifier: LGPL-2.1-or-later
"""GUI smoke test: run inside the full FreeCAD GUI (see tools/run_tests.sh --gui).

Activates the workbench, checks its toolbar, menu and command, and runs
Create Extrusion the way a user would. Exits FreeCAD with status 0 on
success and 1 on failure.
"""

import os
import sys
import traceback
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtWidgets

WB = "TSlotWorkbench"
CMD = "TSlot_CreateExtrusion"


class TestGui(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)
        FreeCADGui.activateWorkbench(WB)

    def tearDown(self):
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)

    def test_workbench_registered(self):
        self.assertIn(WB, FreeCADGui.listWorkbenches())
        wb = FreeCADGui.getWorkbench(WB)
        self.assertEqual(wb.MenuText, "Extrusions")
        self.assertTrue(os.path.isfile(wb.Icon), wb.Icon)
        self.assertEqual(wb.GetClassName(), "Gui::PythonWorkbench")
        self.assertEqual(FreeCADGui.activeWorkbench().name(), WB)

    def test_only_own_toolbar_and_menu(self):
        """We add one toolbar and one menu, and they do not leak into other workbenches."""
        # FreeCAD's standard toolbars/menus are the ones every workbench shares.
        others = {}
        for name in ("PartWorkbench", "SketcherWorkbench"):
            FreeCADGui.activateWorkbench(name)
            other = FreeCADGui.getWorkbench(name)
            others[name] = (set(other.listToolbars()), set(other.listMenus()))
        std_toolbars = set.intersection(*(t for t, _ in others.values()))
        std_menus = set.intersection(*(m for _, m in others.values()))

        FreeCADGui.activateWorkbench(WB)
        wb = FreeCADGui.getWorkbench(WB)
        self.assertEqual(set(wb.listToolbars()) - std_toolbars, {"T-Slot"})
        self.assertEqual(set(wb.listMenus()) - std_menus, {"Extrusions"})
        self.assertEqual(wb.getToolbarItems()["T-Slot"], [CMD])
        for toolbars, menus in others.values():
            self.assertNotIn("T-Slot", toolbars)
            self.assertNotIn("Extrusions", menus)

    def test_toolbar_and_menu_visible(self):
        mw = FreeCADGui.getMainWindow()
        toolbars = [tb for tb in mw.findChildren(QtWidgets.QToolBar) if tb.objectName() == "T-Slot"]
        self.assertEqual(len(toolbars), 1)
        self.assertIn("Create Extrusion", [a.text() for a in toolbars[0].actions()])
        menus = [a.text().replace("&", "") for a in mw.menuBar().actions()]
        self.assertIn("Extrusions", menus)

    def test_command(self):
        self.assertIn(CMD, FreeCADGui.listCommands())
        command = FreeCADGui.Command.get(CMD)
        self.assertTrue(command.isActive())
        self.assertTrue(os.path.isfile(command.getInfo()["pixmap"]))

    def test_create_without_document(self):
        self.assertIsNone(FreeCAD.ActiveDocument)
        FreeCADGui.runCommand(CMD)
        doc = FreeCAD.ActiveDocument
        self.assertIsNotNone(doc)
        self.assertEqual(len(doc.Objects), 1)
        obj = doc.Objects[0]
        bb = obj.Shape.BoundBox
        self.assertEqual((round(bb.XLength, 6), round(bb.YLength, 6), round(bb.ZLength, 6)), (40, 40, 750))
        self.assertEqual(obj.Label, "Extrusion 4040 x 750 mm")
        self.assertEqual([o.Name for o in FreeCADGui.Selection.getSelection()], [obj.Name])
        self.assertTrue(obj.ViewObject.Visibility)

        # User workflow: edit properties, recompute.
        obj.ProfileSize = "3030"
        obj.Length = 1200
        doc.recompute()
        bb = obj.Shape.BoundBox
        self.assertEqual((round(bb.XLength, 6), round(bb.ZLength, 6)), (30, 1200))

    def test_create_is_undoable(self):
        doc = FreeCAD.newDocument()
        FreeCADGui.runCommand(CMD)
        self.assertEqual(len(doc.Objects), 1)
        self.assertEqual(doc.UndoNames[0], "Create Extrusion")
        doc.undo()
        self.assertEqual(len(doc.Objects), 0)

    def test_save_reopen_in_gui(self):
        import tempfile

        FreeCADGui.runCommand(CMD)
        doc = FreeCAD.ActiveDocument
        name = doc.Objects[0].Name
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gui.FCStd")
            doc.saveAs(path)
            FreeCAD.closeDocument(doc.Name)
            doc = FreeCAD.openDocument(path)
            obj = doc.getObject(name)
            self.assertIsNotNone(obj.ViewObject)
            self.assertTrue(obj.ViewObject.Visibility)
            obj.ProfileSize = "2020"
            doc.recompute()
            self.assertAlmostEqual(obj.Shape.BoundBox.XLength, 20.0)
            FreeCAD.closeDocument(doc.Name)


    def test_open_v0_1_document(self):
        """A document saved by v0.1 (rectangular blocks) opens with T-slot geometry."""
        import shutil
        import tempfile

        fixture = os.path.join(os.environ["TSLOT_TESTS_DIR"], "fixtures", "mvp_v0_1.FCStd")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "mvp.FCStd")
            shutil.copy(fixture, path)
            doc = FreeCAD.openDocument(path)
            obj = doc.getObject("Extrusion")
            self.assertTrue(obj.ViewObject.Visibility)
            self.assertLess(obj.Shape.Volume, 40 * 40 * 750 * 0.8)  # no longer a solid block
            self.assertEqual(len(obj.Shape.Solids), 1)
            doc.recompute()
            self.assertTrue(obj.isValid())
            FreeCAD.closeDocument(doc.Name)


def _run():
    # The GUI redirects sys.stdout to the Report view; report to the terminal.
    out = sys.__stdout__
    status = 1
    try:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestGui)
        result = unittest.TextTestRunner(stream=out, verbosity=2).run(suite)
        status = 0 if result.wasSuccessful() else 1
    except Exception:
        traceback.print_exc(file=out)
    out.flush()
    os._exit(status)


# Run once the main window and event loop are up.
QtCore.QTimer.singleShot(0, _run)
