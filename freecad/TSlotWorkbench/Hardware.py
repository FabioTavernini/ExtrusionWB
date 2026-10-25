# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""T-nuts in profile slots, and screws from the Fasteners workbench.

A T-nut sits in one slot of one extrusion: the extrusion, the side, the
slot on that side and the position along the extrusion. Its shape follows
the slot's cavity, so it fits every profile in the catalogue. A nut that
belongs to a corner bracket works out its slot and position from the
bracket's bolt hole on every recompute, so it slides along with the
bracket.

Screws are ``ISO 7380-1`` (button head) or ``ISO 4762`` (socket head)
objects from the Fasteners workbench, attached to a nut with FreeCAD's
attachment: they follow the nut, and stay editable in the Fasteners way.
The screw's ``AttachmentOffset`` Z is the thickness clamped under its head.

The nut frame: origin on the profile's outer face, on the slot centre
line; X along the extrusion, Z out of the profile, Y across the slot.

FreeCAD stores the proxies as ``freecad.TSlotWorkbench.Hardware.TSlotNut``
and ``...ViewProviderTSlotNut`` in saved documents; do not rename them.
"""

import FreeCAD
import Part  # must be imported before FastenersCmd, which crashes FreeCADCmd otherwise

from . import Profiles, icon_path
from .Extrusion import Extrusion

TOL = 1e-3

# Metric threads offered for nuts, with their nominal diameters, in mm.
THREADS = {"M4": 4.0, "M5": 5.0, "M6": 6.0, "M8": 8.0}

# Gap between nut and slot walls, and between nut and slot floor.
SIDE_CLEARANCE = 0.2
FLOOR_CLEARANCE = 1.0

SIDES = ("+X", "-X", "+Y", "-Y")
_SIDE_AXES = {"+X": (0, 1), "-X": (0, -1), "+Y": (1, 1), "-Y": (1, -1)}

BRACKET_SCREW = "ISO7380-1"  # button head: low enough for both heads in a bracket
MANUAL_SCREW = "ISO4762"     # socket head cap screw


# ---------------------------------------------------------------- slots

def _profile(obj):
    return Profiles.get_profile(obj.ProfileFamily, obj.ProfileSize)


def slot_centres(profile, side):
    """Across-coordinates of the slot centre lines on ``side`` (Y for ±X sides, X for ±Y)."""
    axis, _ = _SIDE_AXES[side]
    if axis == 0:
        return [(j + 0.5) * profile.outer - profile.height / 2.0 for j in range(profile.rows)]
    return [(i + 0.5) * profile.outer - profile.width / 2.0 for i in range(profile.columns)]


def slot_frame(extrusion, side, slot, position):
    """Global placement of the nut frame on ``extrusion`` (see the module docstring)."""
    profile = _profile(extrusion)
    centres = slot_centres(profile, side)
    if not 0 <= slot < len(centres):
        raise Profiles.ProfileError(f"{extrusion.Label} has no slot {slot} on side {side}")
    axis, sign = _SIDE_AXES[side]
    half = (profile.width / 2.0, profile.height / 2.0)
    v = FreeCAD.Vector
    if axis == 0:
        origin, out = v(sign * half[0], centres[slot], position), v(sign, 0, 0)
    else:
        origin, out = v(centres[slot], sign * half[1], position), v(0, sign, 0)
    along = v(0, 0, 1)
    across = out.cross(along)
    local = FreeCAD.Placement(FreeCAD.Matrix(along.x, across.x, out.x, origin.x,
                                             along.y, across.y, out.y, origin.y,
                                             along.z, across.z, out.z, origin.z,
                                             0, 0, 0, 1))
    return extrusion.getGlobalPlacement().multiply(local)


def locate_in_slot(extrusion, point, normal, snap=False):
    """Find the slot under ``point`` on the side face of ``extrusion`` facing ``normal``.

    Returns (side, slot, position along the extrusion, distance from the
    slot centre line). Without ``snap``, the point must be on a slot centre
    line; with it, the nearest slot is taken. Raises ``ProfileError`` if
    ``point`` is not on a side face, or (without ``snap``) not over a slot.
    """
    pl = extrusion.getGlobalPlacement()
    local_p = pl.inverse().multVec(point)
    local_n = pl.Rotation.inverted().multVec(normal)
    profile = _profile(extrusion)
    half = (profile.width / 2.0, profile.height / 2.0)
    for side, (axis, sign) in _SIDE_AXES.items():
        if abs(local_n[axis] - sign) > 1e-6:
            continue
        if abs(local_p[axis] - sign * half[axis]) > TOL:
            break
        if not -TOL <= local_p.z <= extrusion.Length.Value + TOL:
            break
        across = local_p[1 - axis]
        centres = slot_centres(profile, side)
        slot = min(range(len(centres)), key=lambda i: abs(centres[i] - across))
        offset = across - centres[slot]
        if not snap and abs(offset) > TOL:
            raise Profiles.ProfileError(
                f"Not over a slot of {extrusion.Label}: {abs(offset):.3f} mm off the slot centre line")
        return side, slot, local_p.z, offset
    raise Profiles.ProfileError(f"Not on a side face of {extrusion.Label}")


def thread_for_slot(slot):
    """The largest thread whose nut neck still fits the slot opening with some wall to spare."""
    fitting = [name for name, d in THREADS.items() if d <= slot.opening - 2.0 * SIDE_CLEARANCE - 1.0]
    if not fitting:
        raise Profiles.ProfileError(f"No nut thread fits a {slot.opening:g} mm slot opening")
    return max(fitting, key=THREADS.get)


# ---------------------------------------------------------------- nut shape

def nut_outline(slot):
    """Cross-section of a nut for ``slot`` as (y, z) points in the nut frame, counter-clockwise.

    The nut has a neck in the slot opening, a body in the cavity that bears
    against the underside of the lips, and a bottom that follows the 45
    degree taper, kept clear of the floor.
    """
    c = SIDE_CLEARANCE
    neck_top = -0.25 * slot.lip
    bottom = slot.depth - FLOOR_CLEARANCE
    if bottom <= slot.taper_start:
        raise Profiles.ProfileError("Slot is too shallow for a T-nut")
    bottom_half = slot.cavity_width / 2.0 - c - (bottom - slot.taper_start)
    right = [
        (slot.opening / 2.0 - c, neck_top),
        (slot.opening / 2.0 - c, -slot.lip),
        (slot.cavity_width / 2.0 - c, -slot.lip),
        (slot.cavity_width / 2.0 - c, -slot.taper_start),
        (bottom_half, -bottom),
    ]
    return [(-y, z) for y, z in right] + [(y, z) for y, z in reversed(right)]


def make_nut_shape(slot, thread):
    """A T-nut for ``slot`` with a plain hole of the ``thread``'s nominal diameter."""
    d = THREADS[thread]
    if d >= slot.opening - 2.0 * SIDE_CLEARANCE:
        raise Profiles.ProfileError(f"An {thread} hole does not fit the nut neck for a {slot.opening:g} mm slot")
    length = slot.cavity_width
    v = FreeCAD.Vector
    pts = [v(-length / 2.0, y, z) for y, z in nut_outline(slot)]
    body = Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(v(length, 0, 0))
    hole = Part.makeCylinder(d / 2.0, slot.depth + 2.0, v(0, 0, -slot.depth - 1.0), v(0, 0, 1))
    shape = body.cut(hole).removeSplitter()
    if len(shape.Solids) != 1 or not shape.isValid():
        raise Profiles.ProfileError(f"T-nut {thread} is not a single valid solid")
    return shape.Solids[0]


# ---------------------------------------------------------------- nut object

class TSlotNut:
    """Proxy for a ``Part::FeaturePython`` T-nut."""

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("App::PropertyLink", "Profile", "Slot", "Extrusion the nut sits in")
        obj.addProperty("App::PropertyEnumeration", "Side", "Slot", "Side of the extrusion, in its local axes")
        obj.addProperty("App::PropertyInteger", "Slot", "Slot", "Slot on that side, counted from 0")
        obj.addProperty("App::PropertyDistance", "Position", "Slot",
                        "Distance along the extrusion from its start")
        obj.addProperty("App::PropertyEnumeration", "Thread", "Nut", "Thread of the nut's hole")
        obj.addProperty("App::PropertyLink", "Bracket", "Bracket",
                        "Corner bracket this nut holds; it then follows the bracket's bolt hole")
        obj.addProperty("App::PropertyEnumeration", "BracketLeg", "Bracket",
                        "Bracket leg: on the bracket's Base or Post extrusion")
        obj.Side = list(SIDES)
        obj.Thread = list(THREADS)
        obj.BracketLeg = ["Base", "Post"]
        obj.setEditorMode("Placement", 1)

    def execute(self, obj):
        if obj.Profile is None:
            raise Profiles.ProfileError("T-nut has no extrusion")
        if obj.Bracket is not None:
            self._follow_bracket(obj)
        slot = _profile(obj.Profile).slot
        obj.Shape = make_nut_shape(slot, obj.Thread)
        obj.Placement = slot_frame(obj.Profile, obj.Side, obj.Slot, obj.Position.Value)

    def _follow_bracket(self, obj):
        from . import Brackets

        bracket = Brackets.get_bracket(obj.Bracket.BracketSize)
        point, normal = bracket_hole(_bracket_placement(obj.Bracket), bracket, obj.BracketLeg)
        side, slot, position, _ = locate_in_slot(obj.Profile, point, normal)
        if obj.Side != side:
            obj.Side = side
        if obj.Slot != slot:
            obj.Slot = slot
        if abs(obj.Position.Value - position) > 1e-9:
            obj.Position = position

    def onChanged(self, obj, prop):
        if prop == "Bracket" and hasattr(obj, "Position"):
            mode = 1 if obj.Bracket is not None else 0
            for name in ("Side", "Slot", "Position"):
                obj.setEditorMode(name, mode)

    def onDocumentRestored(self, obj):
        obj.setEditorMode("Placement", 1)
        self.onChanged(obj, "Bracket")

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


class ViewProviderTSlotNut:
    """Shows the nut's screws under it in the tree."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        return icon_path("TSlotNut.svg")

    def claimChildren(self):
        return screws_of(self.Object)

    def onDelete(self, vobj, subelements):
        doc = vobj.Object.Document
        for screw in screws_of(vobj.Object):
            doc.removeObject(screw.Name)
        return True

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def is_nut(obj):
    return isinstance(getattr(obj, "Proxy", None), TSlotNut)


def screws_of(nut):
    """The screws attached to ``nut``."""
    return [o for o in nut.InList
            if hasattr(o, "AttachmentSupport") and o.AttachmentSupport and o.AttachmentSupport[0][0] == nut]


def bracket_hole(bracket_placement, bracket, leg):
    """Global centre and outward axis of a bracket leg's bolt slot, on the profile face.

    The axis points out of the profile, through the leg.
    """
    mid = (bracket.hole_start + bracket.hole_end) / 2.0
    v = FreeCAD.Vector
    if leg == "Base":
        point, normal = v(0, mid, 0), v(0, 0, 1)
    else:
        point, normal = v(0, 0, mid), v(0, 1, 0)
    return bracket_placement.multVec(point), bracket_placement.Rotation.multVec(normal)


def make_nut(doc, extrusion, side, slot, position, thread=None, name="TSlotNut"):
    """Add a T-nut to ``doc`` and return it. The caller recomputes."""
    if not isinstance(getattr(extrusion, "Proxy", None), Extrusion):
        raise Profiles.ProfileError(f"{extrusion.Label} is not an extrusion")
    thread = thread or thread_for_slot(_profile(extrusion).slot)
    obj = doc.addObject("Part::FeaturePython", name)
    TSlotNut(obj)
    obj.Profile = extrusion
    obj.Side = side
    obj.Slot = slot
    obj.Position = position
    obj.Thread = thread
    obj.Label = f"T-nut {thread}"
    if FreeCAD.GuiUp:
        ViewProviderTSlotNut(obj.ViewObject)
    return obj


def _bracket_placement(bracket_obj):
    """The bracket's placement, worked out from its joint (it may not be recomputed yet)."""
    from .CornerBracket import corner_placement

    return corner_placement(bracket_obj.Post, bracket_obj.PostEnd, bracket_obj.PostSide, bracket_obj.Slot)


def make_bracket_nut(doc, bracket_obj, leg):
    """Add the nut for one leg of a corner bracket. The caller recomputes.

    The nut takes the kit's screw thread, or a smaller one if the slot is
    too narrow for it. Raises ``ProfileError`` if the leg's bolt hole is
    not over a slot.
    """
    from . import Brackets

    extrusion = bracket_obj.Base if leg == "Base" else bracket_obj.Post
    bracket = Brackets.get_bracket(bracket_obj.BracketSize)
    point, normal = bracket_hole(_bracket_placement(bracket_obj), bracket, leg)
    side, slot, position, _ = locate_in_slot(extrusion, point, normal)
    thread = min(bracket.screw, thread_for_slot(_profile(extrusion).slot), key=THREADS.get)
    nut = make_nut(doc, extrusion, side, slot, position, thread)
    nut.Bracket = bracket_obj
    nut.BracketLeg = leg
    return nut


# ---------------------------------------------------------------- screws

def fasteners_available():
    """Whether the Fasteners workbench can be imported."""
    try:
        import FastenersCmd  # noqa: F401
    except ImportError:
        return False
    return True


FASTENERS_MISSING = ("Screws need the Fasteners workbench. Install it with the Addon Manager "
                     "(Tools → Addon manager → Fasteners), then restart FreeCAD.")


def screw_lengths(kind, thread):
    """Standard lengths of a Fasteners screw type, in mm."""
    from FastenersCmd import screwMaker

    return [float(s) for s in screwMaker.GetAllLengths(kind, thread, False)]


def pick_length(kind, thread, longest, preferred=None):
    """The longest standard length up to ``longest`` (and ``preferred``, if given)."""
    limit = min(longest, preferred) if preferred else longest
    fitting = [n for n in screw_lengths(kind, thread) if n <= limit + 1e-9]
    if not fitting:
        raise Profiles.ProfileError(f"No {kind} {thread} screw is {limit:g} mm or shorter")
    return max(fitting)


def max_screw_length(nut, clamp):
    """Longest screw that clamps ``clamp`` mm under its head without touching the slot floor."""
    return clamp + _profile(nut.Profile).slot.depth - 0.5


def make_screw(doc, nut, kind=MANUAL_SCREW, length=None, clamp=0.0, name="Screw"):
    """Add a Fasteners screw into ``nut``, its head ``clamp`` mm above the profile face.

    ``length`` defaults to the longest standard length that stays clear of
    the slot floor. Raises ``ImportError`` without the Fasteners workbench.
    The caller recomputes.
    """
    import FastenersCmd

    thread = nut.Thread
    length = length or pick_length(kind, thread, max_screw_length(nut, clamp))
    obj = doc.addObject("Part::FeaturePython", name)
    FastenersCmd.FSScrewObject(obj, kind, None)
    obj.Diameter = thread
    obj.Length = [_length_name(n) for n in screw_lengths(kind, thread)]
    obj.Length = _length_name(length)
    obj.addExtension("Part::AttachExtensionPython")
    obj.AttachmentSupport = [(nut, "")]
    obj.MapMode = "ObjectXY"
    obj.AttachmentOffset = FreeCAD.Placement(FreeCAD.Vector(0, 0, clamp), FreeCAD.Rotation())
    if FreeCAD.GuiUp:
        FastenersCmd.FSViewProviderTree(obj.ViewObject)
    return obj


def _length_name(length):
    return f"{length:g}"


def make_bracket_hardware(doc, bracket_obj):
    """Add a nut, and a screw if Fasteners is installed, for each leg of a bracket.

    Returns (nuts, screws). The caller recomputes.
    """
    from . import Brackets

    bracket = Brackets.get_bracket(bracket_obj.BracketSize)
    nuts, screws = [], []
    with_screws = fasteners_available()
    for leg in ("Base", "Post"):
        try:
            nut = make_bracket_nut(doc, bracket_obj, leg)
        except Profiles.ProfileError as exc:
            FreeCAD.Console.PrintWarning(f"{bracket_obj.Label}: no T-nut on the {leg.lower()} leg: {exc}\n")
            continue
        nuts.append(nut)
        if with_screws:
            length = pick_length(BRACKET_SCREW, nut.Thread, max_screw_length(nut, bracket.wall),
                                 bracket.screw_length)
            screws.append(make_screw(doc, nut, BRACKET_SCREW, length, bracket.wall))
    return nuts, screws
