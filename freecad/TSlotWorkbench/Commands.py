# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""GUI commands contributed by the Extrusions workbench."""

import FreeCAD
import FreeCADGui

from . import icon_path
from . import Profiles
from .Extrusion import make_extrusion

# Quick-insert buttons, one group (toolbar and submenu) per family:
# family -> (name used in command and icon names, sizes).
QUICK_GROUPS = {
    Profiles.GENERIC_FAMILY: ("Generic", ("2020", "4040", "8080")),
    Profiles.B_TYPE_FAMILY: ("BType", ("2020", "4040", "8080")),
}


class CreateExtrusionCommand:
    """Add a parametric extrusion to the active document.

    Without ``size`` this is the general "Create Extrusion" command, which
    uses the default profile; with one it is a quick-insert for that family
    and size.
    """

    def __init__(self, family=Profiles.DEFAULT_FAMILY, size=None):
        self.family = family
        self.size = size

    def GetResources(self):
        size = self.size or Profiles.DEFAULT_SIZE
        tooltip = (f"Add a parametric T-slot extrusion ({self.family} {size}, "
                   f"{Profiles.DEFAULT_LENGTH:g} mm). Edit its size and length in the property editor.")
        if self.size is None:
            return {
                "MenuText": "Create Extrusion",
                "ToolTip": tooltip,
                "Pixmap": icon_path("CreateExtrusion.svg"),
            }
        return {
            "MenuText": f"Create {self.family} {size} Extrusion",
            "ToolTip": tooltip,
            "Pixmap": icon_path(f"Create{QUICK_GROUPS[self.family][0]}{size}.svg"),
        }

    def IsActive(self):
        # Always available: a document is created if none is open.
        return True

    def Activated(self):
        doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()

        doc.openTransaction("Create Extrusion")
        try:
            obj = make_extrusion(doc, size=self.size or Profiles.DEFAULT_SIZE, family=self.family)
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
# family -> its quick-insert command names, in button order.
QUICK_COMMANDS = {}

FreeCADGui.addCommand("TSlot_CreateExtrusion", CreateExtrusionCommand())
for _family, (_name, _sizes) in QUICK_GROUPS.items():
    QUICK_COMMANDS[_family] = []
    for _size in _sizes:
        _command = f"TSlot_Create{_name}{_size}"
        FreeCADGui.addCommand(_command, CreateExtrusionCommand(_family, _size))
        QUICK_COMMANDS[_family].append(_command)
