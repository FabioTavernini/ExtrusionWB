# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Frames built from extrusions, and fitting existing joints by length.

:func:`make_rectangular_frame` works out every length from the outer
dimensions, so all joints are exact and nothing needs snapping. A box adds
four uprights between a bottom and a top rectangle.

:func:`fit_joints` is the solver for frames that already exist. Snapping a
joint moves the whole post, which breaks any other joint the post is part
of. Fitting instead moves only the post's ends, by changing its ``Length``
(and its placement, for the start end), until each end touches the face it
was meant for. Joints are independent, so a closed loop of members is solved
in one pass.
"""

import itertools

import FreeCAD

from . import CornerBracket, Profiles
from .Extrusion import make_extrusion

BRACKETS = ("Inside", "All", "None")

# How far off a joint may be for fit_joints to correct it, and how far it may be tilted.
FIT_DISTANCE = 50.0  # mm
FIT_ANGLE = 0.01     # degrees
# A post less than one post width in from its base's end, or overhanging it by up to ALIGN_OVERHANG, is
# moved flush with the end. One whose centre is over its base's face is centred on it, or lined up with
# a side of the base if that is nearer.
ALIGN_OVERHANG = 10.0  # mm


def _placement(origin, axis, up):
    """Placement of an extrusion starting at ``origin`` and running along ``axis``,
    with its local Y pointing along ``up``."""
    z = axis
    y = up
    x = y.cross(z)
    m = FreeCAD.Matrix(x.x, y.x, z.x, origin.x,
                       x.y, y.y, z.y, origin.y,
                       x.z, y.z, z.z, origin.z,
                       0, 0, 0, 1)
    return FreeCAD.Placement(m)


def _horizontal(corner):
    """Whether the bracket at ``corner`` lies in a horizontal plane (it sits on a vertical face)."""
    along_base = CornerBracket.corner_frame(corner.post, corner.end, corner.side, corner.slot)[2]
    return abs(along_base.z) < 1e-6


def make_rectangular_frame(doc, width, depth, height=0.0, size=Profiles.DEFAULT_SIZE,
                           family=Profiles.DEFAULT_FAMILY, brackets="Inside", hardware=True):
    """Add a rectangular frame, or with ``height`` a box, whose outer size is
    ``width`` (X) by ``depth`` (Y) by ``height`` (Z), with a corner at the origin.

    Long members run the full width and the short ones fit between them, so
    every joint is exact. In a box each leg is bracketed to both the long and the
    short member of its corner, top and bottom. ``brackets`` is ``"Inside"`` (in the inside corners
    of each rectangle), ``"All"`` (every slot that fits) or ``"None"``; with
    ``hardware`` the brackets get their T-nuts and screws. Returns the group
    holding the members and brackets. The caller recomputes.
    """
    profile = Profiles.get_profile(family, size)
    t, h = profile.width, profile.height  # in the plane / across it
    if brackets not in BRACKETS:
        raise Profiles.ProfileError(f"Brackets must be one of {', '.join(BRACKETS)}, got {brackets!r}")
    for name, value in (("width", width), ("depth", depth)):
        if Profiles.validate_length(value) <= 2 * t:
            raise Profiles.ProfileError(f"The frame {name} must be more than {2 * t:g} mm for {family} {size}")
    box = height not in (0, 0.0, None)
    if box and Profiles.validate_length(height) <= 2 * h:
        raise Profiles.ProfileError(f"The frame height must be more than {2 * h:g} mm for {family} {size}")

    v = FreeCAD.Vector
    x_axis, y_axis, z_axis = v(1, 0, 0), v(0, 1, 0), v(0, 0, 1)
    members = []  # (extrusion, [bases it ends on])

    def member(length, origin, axis, up, name):
        obj = make_extrusion(doc, size=size, length=length, family=family, name=name)
        obj.Placement = _placement(origin, axis, up)
        members.append(obj)
        return obj

    joints = []  # (post, base)

    def rectangle(z, tag):  # returns (front, back, left, right)
        zc = z + h / 2.0
        front = member(width, v(0, t / 2.0, zc), x_axis, z_axis, f"{tag}Front")
        back = member(width, v(0, depth - t / 2.0, zc), x_axis, z_axis, f"{tag}Back")
        left = member(depth - 2 * t, v(t / 2.0, t, zc), y_axis, z_axis, f"{tag}Left")
        right = member(depth - 2 * t, v(width - t / 2.0, t, zc), y_axis, z_axis, f"{tag}Right")
        for post in (left, right):
            joints.extend([(post, front), (post, back)])
        return front, back, left, right

    bottom = rectangle(0.0, "Bottom")
    if box:
        top = rectangle(height - h, "Top")
        # Each leg stands on, and is capped by, the long member of its corner, and meets the short one
        # of that corner along an edge, so it is bracketed to both.
        for x, y, side, end in ((t / 2.0, t / 2.0, 0, 0), (width - t / 2.0, t / 2.0, 1, 0),
                                (t / 2.0, depth - t / 2.0, 0, 1), (width - t / 2.0, depth - t / 2.0, 1, 1)):
            upright = member(height - 2 * h, v(x, y, h), z_axis, y_axis, "Upright")
            for frame in (bottom, top):
                joints.extend([(upright, frame[end]), (upright, frame[2 + side])])

    created = list(members)
    if brackets != "None":
        for post, base in joints:
            corners = CornerBracket.find_corners(post, base)
            if brackets == "Inside":
                corners = [c for c in corners if _horizontal(c)]
            for corner in corners:
                bracket = CornerBracket.make_corner_bracket(doc, corner)
                created.append(bracket)
                if hardware:
                    from . import Hardware

                    Hardware.make_bracket_hardware(doc, bracket)

    group = doc.addObject("App::DocumentObjectGroup", "Frame")
    group.Label = f"Frame {width:g} x {depth:g}" + (f" x {height:g}" if box else "")
    group.addObjects(created)
    return group


# ---------------------------------------------------------------- fitting

def _align_shift(miss):
    """How the post of ``miss`` moves along and across its base to line up with it.

    Returns ``(shift, notes)``: a global vector and what it does, or None if
    nothing moves. Along the base, a post whose side is at most one post width
    in from the end of the base (or overhangs it by a few mm) moves flush with
    that end. Across the base's face, a post whose centre is over the face is moved to
    the nearest of: centred, or a side lined up with a side of the base.
    """
    post, base = miss.post, miss.base
    base_pl = base.getGlobalPlacement()
    rot = base_pl.Rotation
    local = base_pl.inverse().multVec(miss.centre)
    shift, notes = FreeCAD.Vector(), []

    axis = rot.multVec(FreeCAD.Vector(0, 0, 1))
    u = post.getGlobalPlacement().Rotation.inverted().multVec(axis)
    profile = CornerBracket._profile(post)
    half = abs(u.x) * profile.width / 2.0 + abs(u.y) * profile.height / 2.0
    best = None
    # (distance from the end to the post's nearest side, direction towards that end)
    for distance, direction in ((local.z - half, -1.0), (base.Length.Value - local.z - half, 1.0)):
        if abs(distance) <= CornerBracket.TOL or not -ALIGN_OVERHANG <= distance <= 2.0 * half + CornerBracket.TOL:
            continue
        if best is None or abs(distance) < abs(best[0]):
            best = (distance, direction)
    if best is not None:
        shift += axis * (best[1] * best[0])
        notes.append(f"{abs(best[0]):g} mm along {base.Label} to sit flush with its end")

    across_axis = 1 if abs(rot.multVec(FreeCAD.Vector(1, 0, 0)).dot(miss.face_normal)) > 0.5 else 0
    direction = rot.multVec(FreeCAD.Vector(1, 0, 0) if across_axis == 0 else FreeCAD.Vector(0, 1, 0))
    base_profile = CornerBracket._profile(base)
    base_half = (base_profile.width, base_profile.height)[across_axis] / 2.0
    u = post.getGlobalPlacement().Rotation.inverted().multVec(direction)
    post_half = abs(u.x) * profile.width / 2.0 + abs(u.y) * profile.height / 2.0
    across = local[across_axis]
    if abs(across) <= base_half:
        # The post's centre line, or either side lined up with a side of the base.
        flush = base_half - post_half
        candidates = [(0.0, "centre on it")] + [(c, "line up with its side") for c in (flush, -flush) if abs(c) > CornerBracket.TOL]
        target, what = min(candidates, key=lambda c: abs(c[0] - across))
        if CornerBracket.TOL < abs(across - target):
            shift -= direction * (across - target)
            notes.append(f"{abs(across - target):g} mm across {base.Label} to {what}")
    return (shift, notes) if notes else None


def fit_joints(extrusions, max_distance=FIT_DISTANCE):
    """Lengthen or shorten posts so each joint between ``extrusions`` is exact, and
    line up posts that are a little off their base: flush with its end, and centred on its face.

    A joint is the end of one extrusion near a side face of another, square
    to it. The post's end is moved onto the face along its own axis; nothing
    else is moved by a joint, so every joint is fitted from the layout as it was. Returns a
    list of descriptions of what changed. Raises ``ProfileError`` if there is
    nothing to fit.
    """
    plan = {}   # (post, end) -> (gap, base)
    flush = {}  # post -> (shift, notes)
    already = 0
    for a, b in itertools.combinations(extrusions, 2):
        miss = CornerBracket.nearest_miss(a, b)
        if (miss is None or miss.outside > CornerBracket._end_reach(miss.post) + CornerBracket.TOL
                or miss.angle > FIT_ANGLE or abs(miss.gap) > max_distance):
            continue
        shift = _align_shift(miss)
        if shift is not None:
            flush.setdefault(miss.post, shift)
        if abs(miss.gap) <= CornerBracket.TOL:
            already += shift is None
            continue
        plan.setdefault((miss.post, miss.end), (miss.gap, miss.base))

    if not plan and not flush:
        if already:
            raise Profiles.ProfileError(f"The {already} joint(s) between these extrusions already fit.")
        raise Profiles.ProfileError(
            "No joint to fit. The end of one extrusion must be within "
            f"{max_distance:g} mm of a side face of another, at 90 degrees. Tilted joints need Corner Bracket's "
            "snap, or setting an exact Placement.")

    # Work out every change from the layout as it is now, then apply them.
    changes = {post: [post.Length.Value, FreeCAD.Vector()] for post in {p for p, _ in plan} | set(flush)}
    for (post, end), (gap, base) in plan.items():
        changes[post][0] += gap
        if end == "Start":
            axis = post.getGlobalPlacement().Rotation.multVec(FreeCAD.Vector(0, 0, 1))
            changes[post][1] -= axis * gap
    for post, (shift, _) in flush.items():
        changes[post][1] += shift
    for post, (length, _) in changes.items():
        if length <= 0:
            raise Profiles.ProfileError(f"Fitting would make {post.Label} {length:g} mm long.")

    messages = []
    for post, (length, shift) in changes.items():
        old_length = post.Length.Value
        if shift.Length > 1e-9:
            old = post.getGlobalPlacement()
            parent = old.multiply(post.Placement.inverse())
            new = FreeCAD.Placement(shift, FreeCAD.Rotation()).multiply(old)
            post.Placement = parent.inverse().multiply(new)
        post.Length = length
        parts = []
        if abs(length - old_length) > 1e-9:
            ends = " and ".join(e.lower() for (p, e) in plan if p == post)
            bases = ", ".join(sorted({plan[(p, e)][1].Label for (p, e) in plan if p == post}))
            parts.append(f"{old_length:g} to {length:g} mm, so its {ends} meets {bases}")
        if post in flush:
            parts.append("moved " + " and ".join(flush[post][1]))
        messages.append(f"{post.Label}: " + "; ".join(parts))
    return messages
