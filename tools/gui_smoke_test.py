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
# Quick-insert buttons: toolbar/submenu group -> {command: (family, size)}.
QUICK_CMDS = {
    "Generic": {"TSlot_CreateGeneric2020": ("Generic", "2020"),
                "TSlot_CreateGeneric4040": ("Generic", "4040"),
                "TSlot_CreateGeneric8080": ("Generic", "8080")},
    "B-Type": {"TSlot_CreateBType2020": ("B-Type", "2020"),
               "TSlot_CreateBType4040": ("B-Type", "4040"),
               "TSlot_CreateBType8080": ("B-Type", "8080")},
}
BRACKET_CMD = "TSlot_CornerBracket"
NUT_CMD = "TSlot_TSlotNut"
SCREW_CMD = "TSlot_Screw"
QUICK_TOOLBARS = {f"T-Slot {group}" for group in QUICK_CMDS}


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
        """We add our toolbars and one menu, and they do not leak into other workbenches."""
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
        self.assertEqual(set(wb.listToolbars()) - std_toolbars, {"T-Slot"} | QUICK_TOOLBARS)
        self.assertEqual(set(wb.listMenus()) - std_menus, {"Extrusions"})
        items = wb.getToolbarItems()
        self.assertEqual(items["T-Slot"], [CMD, BRACKET_CMD, NUT_CMD, SCREW_CMD])
        for group, commands in QUICK_CMDS.items():
            self.assertEqual(items[f"T-Slot {group}"], list(commands))
        for toolbars, menus in others.values():
            self.assertFalse(({"T-Slot"} | QUICK_TOOLBARS) & set(toolbars))
            self.assertNotIn("Extrusions", menus)

    def test_toolbar_and_menu_visible(self):
        mw = FreeCADGui.getMainWindow()
        def toolbar_texts(name):
            toolbars = [tb for tb in mw.findChildren(QtWidgets.QToolBar) if tb.objectName() == name]
            self.assertEqual(len(toolbars), 1, name)
            self.assertTrue(toolbars[0].isVisible(), name)
            return [a.text() for a in toolbars[0].actions()]

        self.assertIn("Create Extrusion", toolbar_texts("T-Slot"))
        for group, commands in QUICK_CMDS.items():
            texts = toolbar_texts(f"T-Slot {group}")
            for family, size in commands.values():
                self.assertIn(f"Create {family} {size} Extrusion", texts)

        menu_actions = {a.text().replace("&", ""): a for a in mw.menuBar().actions()}
        self.assertIn("Extrusions", menu_actions)
        submenus = {a.text().replace("&", ""): a.menu() for a in menu_actions["Extrusions"].menu().actions()
                    if a.menu() is not None}
        for group, commands in QUICK_CMDS.items():
            self.assertIn(group, submenus)
            texts = [a.text() for a in submenus[group].actions()]
            for family, size in commands.values():
                self.assertIn(f"Create {family} {size} Extrusion", texts)

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

    def test_quick_insert(self):
        doc = FreeCAD.newDocument()
        count = 0
        for commands in QUICK_CMDS.values():
            for cmd, (family, size) in commands.items():
                with self.subTest(cmd=cmd):
                    command = FreeCADGui.Command.get(cmd)
                    self.assertTrue(command.isActive())
                    self.assertTrue(os.path.isfile(command.getInfo()["pixmap"]))
                    FreeCADGui.runCommand(cmd)
                    count += 1
                    obj = doc.Objects[-1]
                    self.assertEqual((obj.ProfileFamily, obj.ProfileSize), (family, size))
                    bb = obj.Shape.BoundBox
                    self.assertAlmostEqual(bb.XLength, int(size[:2]))
                    self.assertAlmostEqual(bb.YLength, int(size[2:]))
                    self.assertAlmostEqual(bb.ZLength, 750.0)
                    self.assertEqual([o.Name for o in FreeCADGui.Selection.getSelection()], [obj.Name])
        self.assertEqual(len(doc.Objects), count)

    def test_corner_bracket(self):
        """Select two extrusions forming an L, run Corner Bracket."""
        doc = FreeCAD.newDocument()
        command = FreeCADGui.Command.get(BRACKET_CMD)
        self.assertTrue(os.path.isfile(command.getInfo()["pixmap"]))
        FreeCADGui.runCommand(CMD)
        base = doc.Objects[-1]
        base.Placement = FreeCAD.Placement(FreeCAD.Vector(), FreeCAD.Rotation(FreeCAD.Vector(0, 1, 0), 90))
        FreeCADGui.runCommand(CMD)
        post = doc.Objects[-1]
        post.Placement.Base = FreeCAD.Vector(20, 0, 20)
        doc.recompute()

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(doc.Name, base.Name)
        self.assertFalse(command.isActive())  # needs two extrusions
        FreeCADGui.Selection.addSelection(doc.Name, post.Name)
        self.assertTrue(command.isActive())
        FreeCADGui.runCommand(BRACKET_CMD)

        from freecad.TSlotWorkbench import CornerBracket, Hardware

        (bracket,) = [o for o in doc.Objects if isinstance(getattr(o, "Proxy", None), CornerBracket.CornerBracket)]
        self.assertEqual(bracket.Label, "Corner bracket 40")
        self.assertTrue(bracket.isValid())
        self.assertTrue(bracket.ViewObject.Visibility)
        self.assertEqual([o.Name for o in FreeCADGui.Selection.getSelection()], [bracket.Name])

        # Hardware: two nuts under the bracket in the tree, a screw under each.
        nuts = CornerBracket.nuts_of(bracket)
        self.assertEqual(len(nuts), 2)
        self.assertEqual(bracket.ViewObject.claimChildren(), nuts)
        expected_objects = 5
        if Hardware.fasteners_available():
            for nut in nuts:
                (screw,) = nut.ViewObject.claimChildren()
                self.assertTrue(screw.isValid(), screw.getStatusString())
                self.assertEqual(screw.Diameter, "M6")  # Generic 4040: 8 mm slot, not the kit M8
            expected_objects = 7
        self.assertEqual(len(doc.Objects), expected_objects)

        self.assertEqual(doc.UndoNames[0], "Corner Bracket")
        doc.undo()
        self.assertEqual(len(doc.Objects), 2)
        doc.redo()
        self.assertEqual(len(doc.Objects), expected_objects)

        # Deleting the bracket in the GUI takes its hardware with it.
        bracket.ViewObject.Proxy.onDelete(bracket.ViewObject, [])
        doc.removeObject(bracket.Name)
        self.assertEqual(len(doc.Objects), 2)

    def test_nut_and_screw_commands(self):
        doc = FreeCAD.newDocument()
        FreeCADGui.runCommand(CMD)  # a 4040 along Z; its +X face is at X = 20
        bar = doc.Objects[-1]
        nut_cmd = FreeCADGui.Command.get(NUT_CMD)
        screw_cmd = FreeCADGui.Command.get(SCREW_CMD)
        for c in (nut_cmd, screw_cmd):
            self.assertTrue(os.path.isfile(c.getInfo()["pixmap"]))

        face = next(i for i, f in enumerate(bar.Shape.Faces, 1)
                    if f.normalAt(0, 0).x > 0.99 and abs(f.Vertexes[0].Point.x - 20) < 1e-6)
        FreeCADGui.Selection.clearSelection()
        self.assertFalse(nut_cmd.isActive())
        FreeCADGui.Selection.addSelection(doc.Name, bar.Name)
        self.assertFalse(nut_cmd.isActive())  # whole object: no point to put it at
        FreeCADGui.Selection.clearSelection()
        point = bar.Shape.Faces[face - 1].CenterOfMass
        FreeCADGui.Selection.addSelection(doc.Name, bar.Name, f"Face{face}", point.x, point.y, point.z)
        self.assertTrue(nut_cmd.isActive())
        FreeCADGui.runCommand(NUT_CMD)

        nut = doc.Objects[-1]
        self.assertEqual(nut.Label, "T-nut M6")  # Generic 4040: 8 mm slot
        self.assertEqual(nut.Side, "+X")
        self.assertAlmostEqual(nut.Position.Value, point.z, places=6)
        self.assertTrue(nut.isValid())
        self.assertEqual(doc.UndoNames[0], "T-Nut")
        self.assertEqual([o.Name for o in FreeCADGui.Selection.getSelection()], [nut.Name])

        from freecad.TSlotWorkbench import Hardware

        self.assertTrue(screw_cmd.isActive())
        if not Hardware.fasteners_available():
            return
        FreeCADGui.runCommand(SCREW_CMD)
        screw = doc.Objects[-1]
        self.assertTrue(screw.isValid(), screw.getStatusString())
        self.assertEqual(screw.Type, "ISO4762")
        self.assertEqual(screw.Diameter, "M6")
        self.assertEqual(nut.ViewObject.claimChildren(), [screw])
        self.assertEqual(doc.UndoNames[0], "Screw")

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
