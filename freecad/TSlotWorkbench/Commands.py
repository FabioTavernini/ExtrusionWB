# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""GUI commands contributed by the Extrusions workbench."""

import FreeCAD
import FreeCADGui

from . import icon_path
from .Extrusion import make_extrusion


class CreateExtrusionCommand:
    """Add a default parametric extrusion to the active document."""

    def GetResources(self):
        return {
            "MenuText": "Create Extrusion",
            "ToolTip": "Add a parametric T-slot extrusion (4040, 750 mm). "
                       "Edit its size and length in the property editor.",
            "Pixmap": icon_path("CreateExtrusion.svg"),
        }

    def IsActive(self):
        # Always available: a document is created if none is open.
        return True

    def Activated(self):
        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()

        doc.openTransaction("Create Extrusion")
        try:
            obj = make_extrusion(doc)
            doc.recompute()
            if not obj.isValid():
                raise RuntimeError("; ".join(obj.getStatusString().splitlines()) or "recompute failed")
        except Exception as exc:
            doc.abortTransaction()
            FreeCAD.Console.PrintError(f"Create Extrusion failed: {exc}\n")
            return
        doc.commitTransaction()

        FreeCADGui.Selection.clearSelection()
        FreeCADGui.Selection.addSelection(doc.Name, obj.Name)
        FreeCADGui.SendMsgToActiveView("ViewFit")


COMMANDS = ["TSlot_CreateExtrusion"]

FreeCADGui.addCommand("TSlot_CreateExtrusion", CreateExtrusionCommand())
