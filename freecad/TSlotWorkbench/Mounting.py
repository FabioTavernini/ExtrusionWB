# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Angle brackets for mounting a plate, and adjustable feet.

An angle bracket sits in a slot like a T-nut: it has the extrusion, a side,
a slot and a position along it, and the frame of :func:`Hardware.slot_frame`
(X along the extrusion, Y across the slot, Z out of the face). Leg A lies on
the face; leg B stands out of the face at the bend, ``BendOffset`` from the
slot's centre line along ``Direction``. Its T-nut and screw follow it.

A foot is a stud in the bore at an end of an extrusion; its frame has Z out
of the end, with the origin at the centre of the bore.

FreeCAD stores the proxies as ``freecad.TSlotWorkbench.Mounting.AngleBracket``
and ``...Foot`` (and their view providers) in saved documents; do not rename
them.
"""

from functools import lru_cache

import FreeCAD
import Part

from . import Geometry, Hardware, MountingCatalogue as Catalogue, Profiles, icon_path
from .Extrusion import Extrusion

DIRECTIONS = ("+Y", "-Y")
ENDS = ("Start", "End")


def _profile(obj):
    return Profiles.get_profile(obj.ProfileFamily, obj.ProfileSize)


def _check_extrusion(extrusion):
    if not isinstance(getattr(extrusion, "Proxy", None), Extrusion):
        raise Profiles.ProfileError(f"{extrusion.Label} is not an extrusion")


# ---------------------------------------------------------------- angle bracket

def edge_distance(profile, side, slot, direction):
    """Distance from a slot's centre line to the edge of the face, towards ``direction``."""
    axis = Hardware._SIDE_AXES[side][0]
    half = (profile.width, profile.height)[1 - axis] / 2.0
    centre = Hardware.slot_centres(profile, side)[slot]
    return half - centre if direction == "+Y" else half + centre


def default_direction(extrusion, side, slot, position):
    """The direction that puts the bend upwards, if the face is not horizontal."""
    frame = Hardware.slot_frame(extrusion, side, slot, position)
    up = frame.Rotation.multVec(FreeCAD.Vector(0, 1, 0)).z
    return "-Y" if up < -0.1 else "+Y"


def make_angle_bracket_shape(bracket, bend, direction):
    """The bracket as one solid in the slot frame, with the bend ``bend`` mm along ``direction``."""
    return _angle_bracket_shape(bracket, round(float(bend), 6), direction).copy(False)


@lru_cache(maxsize=64)
def _angle_bracket_shape(bracket, bend, direction):
    w, t, reach = bracket.width, bracket.wall, bracket.reach
    if bend < 2.0 * t or bend < bracket.hole_width / 2.0 + t:
        raise Profiles.ProfileError(f"Angle bracket {bracket.size}: the bend must be at least {2 * t:g} mm "
                                    "from the slot's centre line")
    v = FreeCAD.Vector
    low = min(bend - bracket.leg, -bracket.leg / 2.0)
    body = Part.makeBox(w, bend - low, t, v(-w / 2.0, low, 0)).fuse(Part.makeBox(w, t, reach, v(-w / 2.0, bend - t, 0)))

    r = bracket.hole_width / 2.0
    half = bracket.hole_length / 2.0 - r
    cutters = [Part.makeCylinder(r, t + 2.0, v(x, 0, -1)) for x in (-half, half)]
    cutters.append(Part.makeBox(2.0 * half, 2.0 * r, t + 2.0, v(-half, -r, -1)))
    z = (t + reach) / 2.0
    for x in (-w / 4.0, w / 4.0):
        cutters.append(Part.makeCylinder(bracket.plate_hole / 2.0, t + 2.0, v(x, bend - t - 1.0, z), v(0, 1, 0)))
    shape = body.cut(cutters[0].fuse(cutters[1:])).removeSplitter()
    if direction == "-Y":
        shape = shape.mirror(v(0, 0, 0), v(0, 1, 0))
    if len(shape.Solids) != 1 or not shape.isValid():
        raise Profiles.ProfileError(f"Angle bracket {bracket.size} is not a single valid solid")
    return shape.Solids[0]


class AngleBracket:
    """Proxy for a ``Part::FeaturePython`` angle bracket for mounting a plate."""

    mounts_in_slot = True  # its T-nut follows its Side, Slot and Position

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("App::PropertyLink", "Profile", "Slot", "Extrusion the bracket is bolted to")
        obj.addProperty("App::PropertyEnumeration", "Side", "Slot", "Side of the extrusion, in its local axes")
        obj.addProperty("App::PropertyInteger", "Slot", "Slot", "Slot on that side, counted from 0")
        obj.addProperty("App::PropertyDistance", "Position", "Slot", "Distance along the extrusion from its start")
        obj.addProperty("App::PropertyEnumeration", "BracketSize", "Bracket", "Angle bracket size (profile series)")
        obj.addProperty("App::PropertyEnumeration", "Direction", "Bracket",
                        "Which way across the face, along the slot frame's Y axis, the bend lies")
        obj.addProperty("App::PropertyLength", "BendOffset", "Bracket",
                        "Distance from the slot's centre line to the bend. The default puts the "
                        "ledge flush with the edge of the face")
        obj.Side = list(Hardware.SIDES)
        obj.BracketSize = Catalogue.angle_bracket_sizes()
        obj.Direction = list(DIRECTIONS)
        obj.setEditorMode("Placement", 1)

    def execute(self, obj):
        if obj.Profile is None:
            raise Profiles.ProfileError("Angle bracket has no extrusion")
        bracket = Catalogue.get_angle_bracket(obj.BracketSize)
        obj.Shape = make_angle_bracket_shape(bracket, obj.BendOffset.Value, obj.Direction)
        obj.Placement = Hardware.slot_frame(obj.Profile, obj.Side, obj.Slot, obj.Position.Value)

    def onDocumentRestored(self, obj):
        obj.setEditorMode("Placement", 1)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


class ViewProviderAngleBracket:
    """Shows the bracket's T-nut and screw under it in the tree."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return icon_path("AngleBracket.svg")

    def claimChildren(self):
        from .CornerBracket import nuts_of

        return nuts_of(self.Object)

    def onDelete(self, vobj, subelements):
        from .CornerBracket import nuts_of

        doc = vobj.Object.Document
        for nut in nuts_of(vobj.Object):
            for screw in Hardware.screws_of(nut):
                doc.removeObject(screw.Name)
            doc.removeObject(nut.Name)
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def make_angle_bracket(doc, extrusion, side, slot, position, size=None, direction=None, bend=None,
                       name="AngleBracket"):
    """Add an angle bracket in a slot and return it. The caller recomputes."""
    _check_extrusion(extrusion)
    profile = _profile(extrusion)
    Hardware.slot_centres(profile, side)  # validates the side
    if not 0 <= slot < len(Hardware.slot_centres(profile, side)):
        raise Profiles.ProfileError(f"{extrusion.Label} has no slot {slot} on side {side}")
    bracket = Catalogue.get_angle_bracket(size) if size else Catalogue.angle_bracket_for(profile.outer)
    direction = direction or default_direction(extrusion, side, slot, position)
    if direction not in DIRECTIONS:
        raise Profiles.ProfileError(f"Direction must be one of {', '.join(DIRECTIONS)}, got {direction!r}")
    obj = doc.addObject("Part::FeaturePython", name)
    AngleBracket(obj)
    obj.Profile = extrusion
    obj.Side = side
    obj.Slot = slot
    obj.Position = position
    obj.BracketSize = bracket.size
    obj.Direction = direction
    obj.BendOffset = bend if bend is not None else edge_distance(profile, side, slot, direction)
    obj.Label = f"{bracket.size} angle bracket"
    if FreeCAD.GuiUp:
        ViewProviderAngleBracket(obj.ViewObject)
    return obj


def make_angle_bracket_hardware(doc, bracket_obj):
    """Add a T-nut, and a screw if Fasteners is installed, for an angle bracket.

    Returns (nut, screw or None). The caller recomputes.
    """
    bracket = Catalogue.get_angle_bracket(bracket_obj.BracketSize)
    extrusion = bracket_obj.Profile
    thread = min(bracket.screw, Hardware.thread_for_slot(_profile(extrusion).slot), key=Hardware.THREADS.get)
    nut = Hardware.make_nut(doc, extrusion, bracket_obj.Side, bracket_obj.Slot, bracket_obj.Position.Value, thread)
    nut.Bracket = bracket_obj
    screw = None
    if Hardware.fasteners_available():
        length = Hardware.pick_length(Hardware.BRACKET_SCREW, nut.Thread,
                                      Hardware.max_screw_length(nut, bracket.wall), bracket.screw_length)
        screw = Hardware.make_screw(doc, nut, Hardware.BRACKET_SCREW, length, bracket.wall)
    return nut, screw


# ---------------------------------------------------------------- foot

def make_foot_shape(foot, bore, extension, engage_limit):
    """A foot as one solid, Z out of the extrusion's end, the stud ``extension`` mm clear of it."""
    return _foot_shape(foot, round(float(bore), 6), round(float(extension), 6), round(float(engage_limit), 6)).copy(False)


@lru_cache(maxsize=64)
def _foot_shape(foot, bore, extension, engage_limit):
    if extension <= 0:
        raise Profiles.ProfileError(f"A foot's extension must be positive, got {extension:g}")
    v = FreeCAD.Vector
    engage = min(foot.engage, engage_limit)
    radius = min(foot.nominal, bore - 0.1) / 2.0  # the stud's thread stays inside the bore
    stud = Part.makeCylinder(radius, engage + extension, v(0, 0, -engage))
    pad = Part.makeCylinder(foot.pad_diameter / 2.0, foot.pad_thickness, v(0, 0, extension))
    shape = stud.fuse(pad).removeSplitter()
    if len(shape.Solids) != 1 or not shape.isValid():
        raise Profiles.ProfileError(f"Foot {foot.thread} is not a single valid solid")
    return shape.Solids[0]


def end_frame(extrusion, end, bore):
    """Global placement at the centre of an extrusion's bore at ``end``, Z pointing out of the end."""
    profile = _profile(extrusion)
    centres = Geometry.bore_centres(profile)
    if not 0 <= bore < len(centres):
        raise Profiles.ProfileError(f"{extrusion.Label} has no bore {bore}")
    x, y = centres[bore]
    if end == "End":
        local = FreeCAD.Placement(FreeCAD.Vector(x, y, extrusion.Length.Value), FreeCAD.Rotation())
    else:
        local = FreeCAD.Placement(FreeCAD.Vector(x, y, 0), FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 180))
    return extrusion.getGlobalPlacement().multiply(local)


class Foot:
    """Proxy for a ``Part::FeaturePython`` adjustable foot."""

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("App::PropertyLink", "Profile", "Foot", "Extrusion the foot is screwed into")
        obj.addProperty("App::PropertyEnumeration", "End", "Foot", "Which end of the extrusion")
        obj.addProperty("App::PropertyInteger", "Bore", "Foot", "Bore the stud is in, counted from 0")
        obj.addProperty("App::PropertyEnumeration", "Thread", "Foot", "Thread of the stud")
        obj.addProperty("App::PropertyLength", "Extension", "Foot",
                        "Distance from the end of the extrusion to the pad: set it to level the frame")
        obj.End = list(ENDS)
        obj.Thread = Catalogue.foot_threads()
        obj.setEditorMode("Placement", 1)

    def execute(self, obj):
        if obj.Profile is None:
            raise Profiles.ProfileError("Foot has no extrusion")
        profile = _profile(obj.Profile)
        foot = Catalogue.get_foot(obj.Thread)
        obj.Shape = make_foot_shape(foot, profile.bore_diameter, obj.Extension.Value, obj.Profile.Length.Value)
        obj.Placement = end_frame(obj.Profile, obj.End, obj.Bore)

    def onDocumentRestored(self, obj):
        obj.setEditorMode("Placement", 1)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


class ViewProviderFoot:

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return icon_path("Foot.svg")

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def make_foot(doc, extrusion, end, bore=0, thread=None, extension=None, name="Foot"):
    """Add a foot in a bore at one end of ``extrusion`` and return it. The caller recomputes."""
    _check_extrusion(extrusion)
    if end not in ENDS:
        raise Profiles.ProfileError(f"End must be one of {', '.join(ENDS)}, got {end!r}")
    profile = _profile(extrusion)
    thread = thread or Catalogue.foot_for(profile.outer)
    Catalogue.get_foot(thread)
    end_frame(extrusion, end, bore)  # validates the bore
    obj = doc.addObject("Part::FeaturePython", name)
    Foot(obj)
    obj.Profile = extrusion
    obj.End = end
    obj.Bore = bore
    obj.Thread = thread
    obj.Extension = extension if extension is not None else Catalogue.DEFAULT_EXTENSION
    obj.Label = f"{thread} foot"
    if FreeCAD.GuiUp:
        ViewProviderFoot(obj.ViewObject)
    return obj


def make_feet(doc, extrusion, end, **kwargs):
    """A foot in every bore at ``end`` of ``extrusion``. The caller recomputes."""
    return [make_foot(doc, extrusion, end, bore, **kwargs) for bore in range(len(Geometry.bore_centres(_profile(extrusion))))]


def lower_end(extrusion):
    """The end of ``extrusion`` that is lower in the global Z direction."""
    z = extrusion.getGlobalPlacement().Rotation.multVec(FreeCAD.Vector(0, 0, 1)).z
    return "Start" if z >= 0 else "End"
