# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""TSlotWorkbench: parametric T-slot aluminium extrusions for FreeCAD.

Kept free of FreeCAD imports so that ``Profiles`` can be tested with plain
Python.
"""

import os

# This file is at <addon-root>/freecad/TSlotWorkbench/__init__.py.
ADDON_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ICON_DIR = os.path.join(ADDON_ROOT, "Resources", "Icons")


def icon_path(filename):
    """Absolute path of an icon in ``Resources/Icons``."""
    return os.path.join(ICON_DIR, filename)
