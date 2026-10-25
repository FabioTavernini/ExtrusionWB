# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""FreeCAD startup hook: defines and registers the Extrusions workbench."""

import FreeCADGui

from . import icon_path


class TSlotWorkbench(FreeCADGui.Workbench):
    """Create parametric T-slot aluminium extrusions."""

    MenuText = "Extrusions"
    ToolTip = "Create parametric aluminium extrusions"
    Icon = icon_path("Logo.svg")

    def Initialize(self):
        """Run once, the first time the user activates this workbench."""
        # Importing Commands registers the commands with FreeCADGui.addCommand.
        from . import Commands

        self.appendToolbar("T-Slot", Commands.COMMANDS)
        self.appendMenu("Extrusions", Commands.COMMANDS)
        # One toolbar and one submenu of quick-insert buttons per family.
        for family, commands in Commands.QUICK_COMMANDS.items():
            self.appendToolbar(f"T-Slot {family}", commands)
            self.appendMenu(["Extrusions", family], commands)

    def GetClassName(self):
        """Required for Python workbenches. Must return this exact string."""
        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(TSlotWorkbench())
