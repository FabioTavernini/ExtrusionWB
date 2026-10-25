# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Corner brackets placed in the inside corner of a 90 degree joint.

A joint is two extrusions where the end of one, the *post*, touches a side
face of the other, the *base*, with their axes at 90 degrees. Each inside
corner of the joint is where the base face meets one side face of the post,
at one of that side's slots. :func:`find_corners` lists them.

A bracket object stores its corner as the post, which end of it, which
side and which slot, and works out its placement from the post's current
placement, profile and length on every recompute. It follows the post when
the post moves or changes length. The base is linked too, so the bracket
recomputes after both, and the bracket warns when the base no longer
touches it.

FreeCAD stores the proxy as ``freecad.TSlotWorkbench.CornerBracket.CornerBracket``
in saved documents; do not rename the module or the class.
"""

import math
from collections import namedtuple
from functools import lru_cache

import FreeCAD
import Part

from . import Brackets, Profiles
from .Extrusion import Extrusion

# Distance and direction tolerances for "touching" and "parallel".
TOL = 1e-3
ANGLE_TOL = 1e-6

ENDS = ("Start", "End")
SIDES = ("+X", "-X", "+Y", "-Y")

Corner = namedtuple("Corner", "post base end side slot")
Corner.__doc__ = "An inside corner: the post's end and side, and the slot on that side."


def is_extrusion(obj):
    return isinstance(getattr(obj, "Proxy", None), Extrusion)


def _profile(obj):
    return Profiles.get_profile(obj.ProfileFamily, obj.ProfileSize)


def side_slots(profile, side):
    """Outward normal of ``side`` and the slot centres on it, in the profile's local XY."""
    w, h, u = profile.width / 2.0, profile.height / 2.0, profile.outer
    across_y = [(j + 0.5) * u - h for j in range(profile.rows)]
    across_x = [(i + 0.5) * u - w for i in range(profile.columns)]
    return {
        "+X": ((1, 0), [(w, y) for y in across_y]),
        "-X": ((-1, 0), [(-w, y) for y in across_y]),
        "+Y": ((0, 1), [(x, h) for x in across_x]),
        "-Y": ((0, -1), [(x, -h) for x in across_x]),
    }[side]


def corner_frame(post, end, side, slot):
    """Global origin and axes (corner line, along the base, along the post) of a corner.

    The origin is where the post's end plane, the post's side face and
    the slot's centre line meet.
    """
    profile = _profile(post)
    (nx, ny), slots = side_slots(profile, side)
    if not 0 <= slot < len(slots):
        raise Profiles.ProfileError(f"{post.Label} has no slot {slot} on side {side}")
    x, y = slots[slot]
    z = 0.0 if end == "Start" else post.Length.Value
    end_normal = FreeCAD.Vector(0, 0, -1 if end == "Start" else 1)

    pl = post.getGlobalPlacement()
    rot = pl.Rotation
    origin = pl.multVec(FreeCAD.Vector(x, y, z))
    along_base = rot.multVec(FreeCAD.Vector(nx, ny, 0))
    along_post = rot.multVec(-end_normal)
    corner_line = along_base.cross(along_post)
    return origin, corner_line, along_base, along_post


def corner_placement(post, end, side, slot):
    """Placement mapping the bracket's local frame onto a corner."""
    o, x, y, z = corner_frame(post, end, side, slot)
    m = FreeCAD.Matrix(x.x, y.x, z.x, o.x,
                       x.y, y.y, z.y, o.y,
                       x.z, y.z, z.z, o.z,
                       0, 0, 0, 1)
    return FreeCAD.Placement(m)


def _base_face(base, point, normal):
    """The base's side face that ``point`` lies on with outward ``normal``, as
    (local axis index, sign), or None."""
    pl = base.getGlobalPlacement()
    local_n = pl.Rotation.inverted().multVec(normal)
    local_p = pl.inverse().multVec(point)
    profile = _profile(base)
    half = (profile.width / 2.0, profile.height / 2.0)
    for axis in (0, 1):
        for sign in (1, -1):
            if abs(local_n[axis] - sign) > ANGLE_TOL:
                continue
            if abs(local_p[axis] - sign * half[axis]) > TOL:
                return None
            return axis, sign
    return None


def _on_face(base, axis, point):
    """Whether ``point`` lies within the extent of the base's side face along ``axis``."""
    local = base.getGlobalPlacement().inverse().multVec(point)
    profile = _profile(base)
    half = (profile.width / 2.0, profile.height / 2.0)
    other = 1 - axis
    return abs(local[other]) <= half[other] + TOL and -TOL <= local.z <= base.Length.Value + TOL


def bracket_fits(corner, bracket):
    """Whether ``bracket`` at ``corner`` sits on the base face and along the post."""
    o, c, along_base, along_post = corner_frame(corner.post, corner.end, corner.side, corner.slot)
    # The base face looks back along the post.
    face = _base_face(corner.base, o, along_post)
    if face is None:
        return False
    axis = face[0]
    half = bracket.width / 2.0
    footprint = [o + c * s * half + along_base * d for s in (-1, 1) for d in (0.0, bracket.leg)]
    if not all(_on_face(corner.base, axis, p) for p in footprint):
        return False
    return bracket.leg <= corner.post.Length.Value + TOL


def default_bracket(a, b):
    """The bracket size for a joint: the largest that fits the smaller profile series."""
    return Brackets.bracket_for(min(_profile(a).outer, _profile(b).outer))


def find_corners(a, b, bracket=None):
    """Every inside corner between extrusions ``a`` and ``b`` where ``bracket`` fits.

    Either may be the post. ``bracket`` defaults to :func:`default_bracket`.
    """
    bracket = bracket or default_bracket(a, b)
    corners = []
    for post, base in ((a, b), (b, a)):
        for end in ENDS:
            for side in SIDES:
                for slot in range(len(side_slots(_profile(post), side)[1])):
                    corner = Corner(post, base, end, side, slot)
                    if bracket_fits(corner, bracket):
                        corners.append(corner)
    return corners


def _face_normal(face):
    u0, u1, v0, v1 = face.ParameterRange
    return face.normalAt((u0 + u1) / 2.0, (v0 + v1) / 2.0)


def corner_touches_face(corner, obj, face):
    """Whether ``face`` of ``obj`` is one of the two faces the bracket at ``corner`` sits on."""
    if not isinstance(face, Part.Face) or not isinstance(face.Surface, Part.Plane):
        return False
    o, _, along_base, along_post = corner_frame(corner.post, corner.end, corner.side, corner.slot)
    if obj == corner.base:
        normal = along_post
    elif obj == corner.post:
        normal = along_base
    else:
        return False
    return (_face_normal(face).sub(normal).Length < 1e-4
            and abs((face.Vertexes[0].Point - o).dot(normal)) < TOL)


def filter_by_faces(corners, faces):
    """The corners that sit on every face in ``faces``, a list of (object, face)."""
    return [c for c in corners if all(corner_touches_face(c, obj, f) for obj, f in faces)]


_SIDE_NAMES = {(0, 1): "+X", (0, -1): "-X", (1, 1): "+Y", (1, -1): "-Y"}


# How far off a joint may be for Corner Bracket to snap it into place.
SNAP_DISTANCE = 10.0  # mm of gap or overlap
SNAP_ANGLE = 5.0      # degrees of tilt or twist

Miss = namedtuple("Miss", "post base end side angle gap outside centre face_normal twist")
Miss.__doc__ = """How close the end of ``post`` comes to a joint with a side face of ``base``.

``angle`` is the tilt of the end from the face in degrees; ``gap`` the
distance from the end's centre to the face (negative when inside the base);
``outside`` how far that centre is off the face's extent; ``twist`` how far
the post is turned about its axis from lining up with the base, in degrees.
``centre`` and ``face_normal`` (outward, towards the post) are global."""


def nearest_miss(a, b):
    """The end of one extrusion and side face of the other that come closest to a joint.

    Closeness is a distance: the gap, plus how far the end's centre is off
    the face, plus how far the tilt moves the edge of the post's end. Tilts
    over 45 degrees are not near misses. Returns a :class:`Miss`, or None.
    """
    best = None
    for post, base in ((a, b), (b, a)):
        pl = post.getGlobalPlacement()
        base_pl = base.getGlobalPlacement()
        profile = _profile(base)
        half = (profile.width / 2.0, profile.height / 2.0)
        for end in ENDS:
            z = 0.0 if end == "Start" else post.Length.Value
            centre = pl.multVec(FreeCAD.Vector(0, 0, z))
            end_normal = pl.Rotation.multVec(FreeCAD.Vector(0, 0, -1 if end == "Start" else 1))
            local_c = base_pl.inverse().multVec(centre)
            local_n = base_pl.Rotation.inverted().multVec(end_normal)
            for (axis, sign), side in _SIDE_NAMES.items():
                # The face's outward normal should point straight back at the post.
                cos = max(-1.0, min(1.0, -sign * local_n[axis]))
                angle = math.degrees(math.acos(cos))
                if angle > 45.0:
                    continue
                gap = sign * local_c[axis] - half[axis]
                other = 1 - axis
                outside = max(abs(local_c[other]) - half[other], -local_c.z, local_c.z - base.Length.Value, 0.0)
                key = abs(gap) + outside + _profile(post).outer * math.sin(math.radians(angle))
                if best is None or key < best[0]:
                    face_normal = base_pl.Rotation.multVec(FreeCAD.Vector(*(sign if i == axis else 0 for i in range(3))))
                    twist = _twist(base, face_normal, pl.Rotation)
                    best = (key, Miss(post, base, end, side, angle, gap, outside, centre, face_normal, twist))
    return best[1] if best else None


def _describe_miss(miss):
    where = f"the {miss.end.lower()} of {miss.post.Label} and the {miss.side} face of {miss.base.Label}"
    problems = []
    if miss.angle > 0.01:
        problems.append(f"the end is tilted {miss.angle:.2f} degrees from the face, so they are not at 90 degrees")
    if abs(miss.gap) > TOL:
        problems.append(f"there is a {miss.gap:.3f} mm gap" if miss.gap > 0
                        else f"the end goes {-miss.gap:.3f} mm into the face")
    if miss.outside > TOL:
        problems.append(f"the end's centre is {miss.outside:.3f} mm off the face")
    if abs(miss.twist) > 0.01:
        problems.append(f"{miss.post.Label} is turned {abs(miss.twist):.2f} degrees about its axis, "
                        f"so its sides do not line up with {miss.base.Label}")
    if not problems:
        return None
    return f"Closest is {where}, but " + "; ".join(problems) + "."


def _twist(base, n, rotation):
    """Degrees the post is turned about face normal ``n`` from lining up with the base.

    ``rotation`` is the post's global rotation; only its turn about ``n`` counts.
    """
    post_x = rotation.multVec(FreeCAD.Vector(1, 0, 0))
    base_axis = base.getGlobalPlacement().Rotation.multVec(FreeCAD.Vector(0, 0, 1))
    # Signed angle from the base axis to the post's X, about n, folded to the nearest quarter turn.
    angle = math.degrees(math.atan2(base_axis.cross(post_x).dot(n), base_axis.dot(post_x)))
    return angle - 90.0 * round(angle / 90.0)


def snap_joint(a, b):
    """Move the post of a near-miss joint between ``a`` and ``b`` into exact contact.

    The post is turned about the centre of its end, so it is square to the
    base's face and its sides line up with the base's, then moved onto the
    face. Only near misses are snapped: within ``SNAP_DISTANCE`` and
    ``SNAP_ANGLE``, with the end's centre on the face. Returns a description
    of what moved, or None if nothing was snapped.
    """
    miss = nearest_miss(a, b)
    if miss is None or miss.outside > TOL or abs(miss.gap) > SNAP_DISTANCE or miss.angle > SNAP_ANGLE:
        return None
    post, base = miss.post, miss.base
    old = post.getGlobalPlacement()
    end_normal = old.Rotation.multVec(FreeCAD.Vector(0, 0, -1 if miss.end == "Start" else 1))
    tilt = FreeCAD.Rotation(end_normal, -miss.face_normal)
    twist = _twist(base, miss.face_normal, tilt.multiply(old.Rotation))
    if abs(twist) > SNAP_ANGLE:
        return None
    turn = FreeCAD.Rotation(miss.face_normal, -twist).multiply(tilt)
    c = miss.centre
    # Turn about the end's centre, then close the gap along the face normal.
    move = (FreeCAD.Placement(c - miss.face_normal * miss.gap, FreeCAD.Rotation())
            .multiply(FreeCAD.Placement(FreeCAD.Vector(), turn))
            .multiply(FreeCAD.Placement(-c, FreeCAD.Rotation())))
    new = move.multiply(old)
    parent = old.multiply(post.Placement.inverse())
    post.Placement = parent.inverse().multiply(new)

    done = []
    if abs(miss.gap) > TOL:
        done.append(f"closed a {miss.gap:.3f} mm gap" if miss.gap > 0
                    else f"pulled it {-miss.gap:.3f} mm out of the face")
    if miss.angle > 1e-6:
        done.append(f"straightened a {miss.angle:.2f} degree tilt")
    if abs(twist) > 1e-6:
        done.append(f"turned it {abs(twist):.2f} degrees to line up")
    if not done:
        return None
    return f"Snapped {post.Label} onto {base.Label}: " + ", ".join(done) + "."


def explain_no_corner(a, b, faces=()):
    """Why :func:`make_corner_brackets` found no corner, for the user."""
    corners = find_corners(a, b)
    if corners and faces:
        names = ", ".join(sorted({obj.Label for obj, _ in faces}))
        return (f"{len(corners)} inside corner(s) found between {a.Label} and {b.Label}, but no bracket "
                f"there sits on the selected face(s) of {names}. Clear the selection and select just "
                "the two extrusions to add them all, or select the faces a bracket should sit on.")
    message = (f"No inside corner between {a.Label} and {b.Label}. The end of one must touch a side "
               "face of the other, at 90 degrees, with room for the bracket on that face.")
    miss = nearest_miss(a, b)
    text = _describe_miss(miss) if miss else None
    if text:
        message += (f" {text} That is too far off to snap into place (more than {SNAP_DISTANCE:g} mm or "
                    f"{SNAP_ANGLE:g} degrees); move it closer, or set exact values in its Placement.")
    return message


class CornerBracket:
    """Proxy for a ``Part::FeaturePython`` corner bracket."""

    def __init__(self, obj):
        obj.Proxy = self
        obj.addProperty("App::PropertyLink", "Post", "Joint",
                        "Extrusion whose end meets the base; the bracket follows it")
        obj.addProperty("App::PropertyLink", "Base", "Joint", "Extrusion whose side face the post's end touches")
        obj.addProperty("App::PropertyEnumeration", "PostEnd", "Joint", "Which end of the post is at the joint")
        obj.addProperty("App::PropertyEnumeration", "PostSide", "Joint",
                        "Side of the post (in its local axes) the bracket sits on")
        obj.addProperty("App::PropertyInteger", "Slot", "Joint", "Slot on that side, counted from 0")
        obj.addProperty("App::PropertyEnumeration", "BracketSize", "Bracket", "Bracket size (profile series)")
        obj.PostEnd = list(ENDS)
        obj.PostSide = list(SIDES)
        obj.BracketSize = Brackets.sizes()
        # The placement is computed from the joint.
        obj.setEditorMode("Placement", 1)

    def execute(self, obj):
        if obj.Post is None:
            raise Profiles.ProfileError("Corner bracket has no post")
        bracket = Brackets.get_bracket(obj.BracketSize)
        obj.Shape = make_bracket_shape(bracket)
        obj.Placement = corner_placement(obj.Post, obj.PostEnd, obj.PostSide, obj.Slot)
        if obj.Base is not None:
            corner = Corner(obj.Post, obj.Base, obj.PostEnd, obj.PostSide, obj.Slot)
            if not bracket_fits(corner, bracket):
                FreeCAD.Console.PrintWarning(
                    f"{obj.Label}: no longer sits on {obj.Base.Label}; it follows {obj.Post.Label}.\n")

    def onDocumentRestored(self, obj):
        obj.setEditorMode("Placement", 1)

    def dumps(self):
        return None

    def loads(self, state):
        return None

    __getstate__ = dumps
    __setstate__ = loads


def _slotted_hole(bracket, along, through):
    """Stadium-shaped prism for a leg's bolt slot.

    ``along`` is the leg's direction from the corner (local Y or Z) and
    ``through`` the direction through the leg's thickness.
    """
    r = bracket.hole_width / 2.0
    start = bracket.hole_start + r
    end = bracket.hole_end - r
    depth = bracket.wall + 2.0
    base = through * -1.0
    centres = [along * start + base, along * end + base]
    parts = [Part.makeCylinder(r, depth, c, through) for c in centres]
    if end > start:
        across = FreeCAD.Vector(1, 0, 0)
        corner = base + along * start - across * r
        p = [corner, corner + across * 2 * r, corner + across * 2 * r + along * (end - start),
             corner + along * (end - start)]
        face = Part.Face(Part.makePolygon(p + [p[0]]))
        parts.append(face.extrude(through * depth))
    return parts[0].fuse(parts[1:])


def make_bracket_shape(bracket):
    """The bracket as one solid in its local frame (see ``Brackets``)."""
    return _bracket_shape(bracket).copy(False)


@lru_cache(maxsize=None)
def _bracket_shape(bracket):
    # Cached: a recompute usually only moves the bracket.
    w, leg, t = bracket.width, bracket.leg, bracket.wall
    v = FreeCAD.Vector
    base_leg = Part.makeBox(w, leg, t, v(-w / 2.0, 0, 0))
    post_leg = Part.makeBox(w, t, leg, v(-w / 2.0, 0, 0))
    cheeks = []
    for x in (-w / 2.0, w / 2.0 - t):
        tri = Part.Face(Part.makePolygon([v(x, 0, 0), v(x, leg, 0), v(x, 0, leg), v(x, 0, 0)]))
        cheeks.append(tri.extrude(v(t, 0, 0)))
    body = base_leg.fuse([post_leg] + cheeks).removeSplitter()
    holes = _slotted_hole(bracket, v(0, 1, 0), v(0, 0, 1)).fuse(_slotted_hole(bracket, v(0, 0, 1), v(0, 1, 0)))
    shape = body.cut(holes).removeSplitter()
    if len(shape.Solids) != 1 or not shape.isValid():
        raise Profiles.ProfileError(f"Bracket {bracket.size} is not a single valid solid")
    return shape.Solids[0]


class ViewProviderCornerBracket:
    """Shows the bracket's T-nuts (and their screws) under it in the tree."""

    def __init__(self, vobj):
        vobj.Proxy = self

    def attach(self, vobj):
        self.Object = vobj.Object

    def getIcon(self):
        from . import icon_path

        return icon_path("CornerBracket.svg")

    def claimChildren(self):
        return nuts_of(self.Object)

    def onDelete(self, vobj, subelements):
        from . import Hardware

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


def nuts_of(bracket_obj):
    """The T-nuts that belong to a bracket."""
    from . import Hardware

    return [o for o in bracket_obj.InList if Hardware.is_nut(o) and o.Bracket == bracket_obj]


def make_corner_bracket(doc, corner, size=None, name="CornerBracket"):
    """Add a bracket at ``corner`` to ``doc`` and return it. The caller recomputes."""
    bracket = Brackets.get_bracket(size) if size else default_bracket(corner.post, corner.base)
    obj = doc.addObject("Part::FeaturePython", name)
    CornerBracket(obj)
    obj.Post = corner.post
    obj.Base = corner.base
    obj.PostEnd = corner.end
    obj.PostSide = corner.side
    obj.Slot = corner.slot
    obj.BracketSize = bracket.size
    obj.Label = f"Corner bracket {bracket.size}"
    if FreeCAD.GuiUp:
        ViewProviderCornerBracket(obj.ViewObject)
    return obj


def make_corner_brackets(doc, a, b, faces=(), hardware=False):
    """Add a bracket in every inside corner between ``a`` and ``b``.

    ``faces``, a list of (object, face), keeps only the corners whose
    bracket sits on all of them. With ``hardware``, each bracket also gets
    its T-nuts and (with the Fasteners workbench) screws. Returns the new
    brackets (possibly none). The caller recomputes.
    """
    corners = filter_by_faces(find_corners(a, b), faces)
    brackets = [make_corner_bracket(doc, c) for c in corners]
    if hardware:
        from . import Hardware

        for obj in brackets:
            Hardware.make_bracket_hardware(doc, obj)
    return brackets
