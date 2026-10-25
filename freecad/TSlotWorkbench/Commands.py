# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""GUI commands contributed by the Extrusions workbench."""

import FreeCAD
import FreeCADGui

from . import icon_path
from . import Profiles
from .Extrusion import make_extrusion

# Sizes that get their own quick-insert button, next to the default one.
QUICK_SIZES = ("2020", "3030", "4040")


class CreateExtrusionCommand:
    """Add a parametric extrusion to the active document.

    Without ``size`` this is the general "Create Extrusion" command, which
    uses the default profile; with one it is a quick-insert for that size.
    """

    def __init__(self, size=None):
        self.size = size

    def GetResources(self):
        size = self.size or Profiles.DEFAULT_SIZE
        tooltip = (f"Add a parametric T-slot extrusion ({size}, {Profiles.DEFAULT_LENGTH:g} mm). "
                   "Edit its size and length in the property editor.")
        if self.size is None:
            return {
                "MenuText": "Create Extrusion",
                "ToolTip": tooltip,
                "Pixmap": icon_path("CreateExtrusion.svg"),
            }
        return {
            "MenuText": f"Create {size} Extrusion",
            "ToolTip": tooltip,
            "Pixmap": icon_path(f"CreateExtrusion{size}.svg"),
        }

    def IsActive(self):
        # Always available: a document is created if none is open.
        return True

    def Activated(self):
        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()

        doc.openTransaction("Create Extrusion")
        try:
            obj = make_extrusion(doc, size=self.size or Profiles.DEFAULT_SIZE)
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


COMMANDS = ["TSlot_CreateExtrusion"] + [f"TSlot_CreateExtrusion{size}" for size in QUICK_SIZES]

FreeCADGui.addCommand("TSlot_CreateExtrusion", CreateExtrusionCommand())
for _size in QUICK_SIZES:
    FreeCADGui.addCommand(f"TSlot_CreateExtrusion{_size}", CreateExtrusionCommand(_size))
