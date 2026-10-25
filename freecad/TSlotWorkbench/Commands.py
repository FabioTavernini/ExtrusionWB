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


class CornerBracketCommand:
    """Add corner brackets to the joint between two selected extrusions."""

    def GetResources(self):
        return {
            "MenuText": "Corner Bracket",
            "ToolTip": "Select two extrusions that meet at 90 degrees (the end of one touching a side "
                       "of the other) to add a bracket in every inside corner of the joint, with its "
                       "T-nuts and screws. Also select the faces a bracket should sit on to add just that one.",
            "Pixmap": icon_path("CornerBracket.svg"),
        }

    def IsActive(self):
        return len(_selected_extrusions()[0]) == 2

    def Activated(self):
        from . import CornerBracket, Hardware

        extrusions, faces = _selected_extrusions()
        if len(extrusions) != 2:
            return
        a, b = extrusions
        doc = a.Document
        doc.openTransaction("Corner Bracket")
        try:
            brackets = CornerBracket.make_corner_brackets(doc, a, b, faces, hardware=True)
            if not brackets:
                raise RuntimeError(CornerBracket.explain_no_corner(a, b, faces))
            doc.recompute()
            for obj in brackets:
                if not obj.isValid():
                    raise RuntimeError("; ".join(obj.getStatusString().splitlines()) or "recompute failed")
        except Exception as exc:
            doc.abortTransaction()
            FreeCAD.Console.PrintError(f"Corner Bracket failed: {exc}\n")
            return
        doc.commitTransaction()
        if not Hardware.fasteners_available():
            FreeCAD.Console.PrintWarning(f"Corner Bracket: T-nuts added without screws. {Hardware.FASTENERS_MISSING}\n")

        FreeCADGui.Selection.clearSelection()
        for obj in brackets:
            FreeCADGui.Selection.addSelection(doc.Name, obj.Name)


class TSlotNutCommand:
    """Add a T-nut in the slot under each clicked point on an extrusion's face."""

    def GetResources(self):
        return {
            "MenuText": "T-Nut",
            "ToolTip": "Click a side face of an extrusion where the nut should go (Ctrl+click for more): "
                       "a T-nut is added in the nearest slot at that point. Move it later with its Position.",
            "Pixmap": icon_path("TSlotNut.svg"),
        }

    def IsActive(self):
        return bool(_picked_faces())

    def Activated(self):
        from . import Hardware

        picks = _picked_faces()
        doc = picks[0][0].Document
        doc.openTransaction("T-Nut")
        try:
            nuts = []
            for obj, face, point in picks:
                normal = face.normalAt(*face.Surface.parameter(point))
                side, slot, position, _ = Hardware.locate_in_slot(obj, point, normal, snap=True)
                nuts.append(Hardware.make_nut(doc, obj, side, slot, position))
            doc.recompute()
            for nut in nuts:
                if not nut.isValid():
                    raise RuntimeError("; ".join(nut.getStatusString().splitlines()) or "recompute failed")
        except Exception as exc:
            doc.abortTransaction()
            FreeCAD.Console.PrintError(f"T-Nut failed: {exc}\n")
            return
        doc.commitTransaction()

        FreeCADGui.Selection.clearSelection()
        for nut in nuts:
            FreeCADGui.Selection.addSelection(doc.Name, nut.Name)


class ScrewCommand:
    """Add a Fasteners screw into each selected T-nut."""

    def GetResources(self):
        return {
            "MenuText": "Screw",
            "ToolTip": "Select T-nuts to screw an ISO 4762 socket head screw into each (needs the Fasteners "
                       "workbench). Set its AttachmentOffset Z to the thickness of the part you are mounting, "
                       "and pick its Length.",
            "Pixmap": icon_path("Screw.svg"),
        }

    def IsActive(self):
        return bool(_selected_nuts())

    def Activated(self):
        from . import Hardware

        nuts = _selected_nuts()
        if not Hardware.fasteners_available():
            FreeCAD.Console.PrintError(f"Screw failed: {Hardware.FASTENERS_MISSING}\n")
            return
        doc = nuts[0].Document
        doc.openTransaction("Screw")
        try:
            screws = [Hardware.make_screw(doc, nut) for nut in nuts]
            doc.recompute()
            for screw in screws:
                if not screw.isValid():
                    raise RuntimeError("; ".join(screw.getStatusString().splitlines()) or "recompute failed")
        except Exception as exc:
            doc.abortTransaction()
            FreeCAD.Console.PrintError(f"Screw failed: {exc}\n")
            return
        doc.commitTransaction()

        FreeCADGui.Selection.clearSelection()
        for screw in screws:
            FreeCADGui.Selection.addSelection(doc.Name, screw.Name)


def _picked_faces():
    """Selected faces of extrusions, as (extrusion, face, picked point)."""
    from .Extrusion import Extrusion

    picks = []
    for sel in FreeCADGui.Selection.getSelectionEx():
        if not isinstance(getattr(sel.Object, "Proxy", None), Extrusion):
            continue
        for sub, point in zip(sel.SubObjects, sel.PickedPoints):
            if sub.ShapeType == "Face":
                picks.append((sel.Object, sub, point))
    return picks


def _selected_nuts():
    from .Hardware import TSlotNut

    return [o for o in FreeCADGui.Selection.getSelection() if isinstance(getattr(o, "Proxy", None), TSlotNut)]


def _selected_extrusions():
    """The distinct selected extrusions, and the selected faces as (object, face)."""
    from .Extrusion import Extrusion

    extrusions, faces = [], []
    for sel in FreeCADGui.Selection.getSelectionEx():
        obj = sel.Object
        if not isinstance(getattr(obj, "Proxy", None), Extrusion):
            continue
        if obj not in extrusions:
            extrusions.append(obj)
        faces.extend((obj, sub) for sub in sel.SubObjects if sub.ShapeType == "Face")
    return extrusions, faces


COMMANDS = ["TSlot_CreateExtrusion", "TSlot_CornerBracket", "TSlot_TSlotNut", "TSlot_Screw"]
# family -> its quick-insert command names, in button order.
QUICK_COMMANDS = {}

FreeCADGui.addCommand("TSlot_CreateExtrusion", CreateExtrusionCommand())
FreeCADGui.addCommand("TSlot_CornerBracket", CornerBracketCommand())
FreeCADGui.addCommand("TSlot_TSlotNut", TSlotNutCommand())
FreeCADGui.addCommand("TSlot_Screw", ScrewCommand())
for _family, (_name, _sizes) in QUICK_GROUPS.items():
    QUICK_COMMANDS[_family] = []
    for _size in _sizes:
        _command = f"TSlot_Create{_name}{_size}"
        FreeCADGui.addCommand(_command, CreateExtrusionCommand(_family, _size))
        QUICK_COMMANDS[_family].append(_command)
