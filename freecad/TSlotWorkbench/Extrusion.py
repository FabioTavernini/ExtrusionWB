# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""The parametric T-slot extrusion document object.

FreeCAD stores the proxy as ``freecad.TSlotWorkbench.Extrusion.Extrusion``
in saved documents and looks it up by that path when they are reopened.
Renaming this module or the class breaks existing files unless a
compatibility alias is kept.
"""

import FreeCAD

from . import Geometry, Profiles

# Version of this object's properties and geometry. Bump it when a change
# needs onDocumentRestored to upgrade older documents.
#   1: v0.1, rectangular envelope (no SchemaVersion property)
#   2: v0.2, T-slot cross-section
SCHEMA_VERSION = 2

_FAMILY_DOC = "Profile family. 'Generic' uses illustrative dimensions, not a manufacturer's specification."

# Property attribute bits for addProperty(): ReadOnly | Output. Output keeps
# the value from touching the object when execute() writes it.
_PROP_READONLY_OUTPUT = 1 | 8


class Extrusion:
    """Proxy for a ``Part::FeaturePython`` holding one straight extrusion."""

    def __init__(self, obj):
        obj.Proxy = self

        obj.addProperty("App::PropertyEnumeration", "ProfileFamily", "Profile", _FAMILY_DOC)
        obj.addProperty("App::PropertyEnumeration", "ProfileSize", "Profile", "Nominal profile size")
        obj.addProperty("App::PropertyLength", "Length", "Extrusion", "Length along the local Z axis")
        obj.addProperty(
            "App::PropertyArea", "CrossSectionArea", "Profile",
            "Cross-section area of the generated geometry (calculated)",
            _PROP_READONLY_OUTPUT,
        )
        obj.addProperty(
            "App::PropertyString", "AutoLabel", "Base",
            "Last label generated automatically; the label is only updated while it still matches this",
            _PROP_READONLY_OUTPUT | 4,  # Hidden
        )
        _add_schema_version(obj)

        obj.ProfileFamily = Profiles.families()
        obj.ProfileFamily = Profiles.DEFAULT_FAMILY
        obj.ProfileSize = Profiles.sizes(Profiles.DEFAULT_FAMILY)
        obj.ProfileSize = Profiles.DEFAULT_SIZE
        obj.Length = Profiles.DEFAULT_LENGTH
        obj.AutoLabel = obj.Label

    def execute(self, obj):
        profile = Profiles.get_profile(obj.ProfileFamily, obj.ProfileSize)
        length = Profiles.validate_length(obj.Length.Value)

        face = Geometry.create_profile_face(profile)
        solid = Geometry.create_extrusion_shape(profile, length)

        # Assigning Shape overwrites Placement with the shape's own, so keep it.
        placement = obj.Placement
        obj.Shape = solid
        obj.Placement = placement

        if abs(obj.CrossSectionArea.Value - face.Area) > 1e-9:
            obj.CrossSectionArea = face.Area
        self._update_label(obj, profile, length)

    def onDocumentRestored(self, obj):
        if not hasattr(obj, "SchemaVersion"):
            # v0.1 document: same properties, but its stored shape is the old
            # rectangular envelope. Rebuild it now; FreeCAD clears the touched
            # flag after restoring, so touch() would not trigger a recompute.
            _add_schema_version(obj)
            if hasattr(obj, "setDocumentationOfProperty"):
                obj.setDocumentationOfProperty("ProfileFamily", _FAMILY_DOC)
            try:
                self.execute(obj)
            except Exception as exc:
                FreeCAD.Console.PrintWarning(f"{obj.Label}: could not upgrade geometry: {exc}\n")

        # Refresh enumeration choices from the current catalogue, so documents
        # saved by an older version pick up newly added families and sizes.
        _set_choices(obj, "ProfileFamily", Profiles.families())
        try:
            _set_choices(obj, "ProfileSize", Profiles.sizes(obj.ProfileFamily))
        except Profiles.ProfileError as exc:
            FreeCAD.Console.PrintWarning(f"{obj.Label}: {exc}\n")

    def _update_label(self, obj, profile, length):
        """Rename the object after its profile, unless the user renamed it."""
        if obj.Label != obj.AutoLabel:
            return
        label = f"Extrusion {profile.size} x {length:g} mm"
        if obj.Label != label:
            obj.Label = label
            # FreeCAD may add a suffix to keep labels unique; remember the result.
            obj.AutoLabel = obj.Label

    def dumps(self):
        # All state lives in document properties.
        return None

    def loads(self, state):
        return None

    # Pre-1.0 names for dumps/loads.
    __getstate__ = dumps
    __setstate__ = loads


def _add_schema_version(obj):
    obj.addProperty(
        "App::PropertyInteger", "SchemaVersion", "Base",
        "Version of the TSlotWorkbench object layout",
        _PROP_READONLY_OUTPUT | 4,  # Hidden
    )
    obj.SchemaVersion = SCHEMA_VERSION


def _set_choices(obj, name, choices):
    """Replace an enumeration's choices, keeping its value when still valid."""
    current = getattr(obj, name)
    if obj.getEnumerationsOfProperty(name) == choices:
        return
    setattr(obj, name, choices)
    if current in choices:
        setattr(obj, name, current)


def make_extrusion(doc, size=Profiles.DEFAULT_SIZE, length=Profiles.DEFAULT_LENGTH,
                   family=Profiles.DEFAULT_FAMILY, name="Extrusion"):
    """Add an extrusion to ``doc`` and return it. The caller recomputes."""
    Profiles.get_profile(family, size)
    Profiles.validate_length(length)

    obj = doc.addObject("Part::FeaturePython", name)
    Extrusion(obj)
    obj.ProfileFamily = family
    obj.ProfileSize = size
    obj.Length = length
    if FreeCAD.GuiUp:
        # No custom view provider is needed; this gives the default Part one.
        obj.ViewObject.Proxy = 0
    return obj
