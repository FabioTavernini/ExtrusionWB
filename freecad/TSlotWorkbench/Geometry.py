# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Cross-section and solid construction for T-slot profiles.

The cross-section is built directly as one face, with no Booleans between
solids:

1. :func:`outline_points` traces the outer boundary as a single closed
   polygon. It walks the four sides clockwise, and each unit edge along a
   side contributes its T-slot recess (opening, undercut cavity, taper,
   floor).
2. Each unit's centre bore is a circle, used as an inner wire of the face.
3. The face is extruded along +Z into one solid.

The section is centred on the local Z axis and the solid runs from Z = 0
to Z = length.

Shapes are cached by profile (and length), since a recompute often only
moves an object: callers get a cheap copy that shares the geometry.
"""

from functools import lru_cache

import FreeCAD
import Part

from . import Profiles


def slot_points(slot):
    """Points of one slot recess in its own (u, v) frame, left to right.

    ``u`` runs along the side, ``v`` inwards from the outer face; see
    ``Profiles`` for the parameters.
    """
    a = slot.opening / 2.0
    b = slot.cavity_width / 2.0
    c = slot.floor_width / 2.0
    left = [
        (-a, 0.0),
        (-a, slot.lip),
        (-b, slot.lip),
        (-b, slot.taper_start),
        (-c, slot.depth),
    ]
    right = [(-u, v) for u, v in reversed(left)]
    return left + right


def outline_points(profile):
    """The closed outer boundary as (x, y) tuples, clockwise, without repeating the start."""
    w = profile.width / 2.0
    h = profile.height / 2.0
    slot = slot_points(profile.slot)
    points = []
    # Each side: start corner, direction along the side, inward normal, and
    # its number of units. Clockwise from the top-left corner.
    for (x0, y0), (dx, dy), (nx, ny), count in (
        ((-w, h), (1, 0), (0, -1), profile.columns),   # top, towards +X
        ((w, h), (0, -1), (-1, 0), profile.rows),      # right, towards -Y
        ((w, -h), (-1, 0), (0, 1), profile.columns),   # bottom, towards -X
        ((-w, -h), (0, 1), (1, 0), profile.rows),      # left, towards +Y
    ):
        points.append((x0, y0))
        for k in range(count):
            centre = (k + 0.5) * profile.outer
            for u, v in slot:
                along = centre + u
                points.append((x0 + dx * along + nx * v, y0 + dy * along + ny * v))
    return points


def bore_centres(profile):
    """Centre of each unit's bore, as (x, y) tuples."""
    return [((i + 0.5) * profile.outer - profile.width / 2.0,
             (j + 0.5) * profile.outer - profile.height / 2.0)
            for j in range(profile.rows) for i in range(profile.columns)]


def create_profile_face(profile):
    """Return the cross-section of ``profile`` as a valid ``Part.Face`` in the XY plane."""
    return _profile_face(profile).copy(False)


@lru_cache(maxsize=None)
def _profile_face(profile):
    outer = Part.makePolygon([FreeCAD.Vector(x, y, 0.0) for x, y in outline_points(profile)], True)
    bores = [Part.Wire(Part.makeCircle(profile.bore_diameter / 2.0, FreeCAD.Vector(x, y, 0.0)))
             for x, y in bore_centres(profile)]
    face = Part.makeFace([outer] + bores, "Part::FaceMakerBullseye")
    if not isinstance(face, Part.Face):
        faces = face.Faces
        if len(faces) != 1:
            raise Profiles.ProfileError(f"Cross-section of {profile.size} produced {len(faces)} faces")
        face = faces[0]
    if not face.isValid():
        raise Profiles.ProfileError(f"Cross-section of {profile.size} is not a valid face")
    return face


def create_extrusion_shape(profile, length):
    """Return ``profile`` extruded ``length`` mm along +Z as one valid solid."""
    return _extrusion_shape(profile, Profiles.validate_length(length)).copy(False)


@lru_cache(maxsize=256)
def _extrusion_shape(profile, length):
    solid = _profile_face(profile).extrude(FreeCAD.Vector(0.0, 0.0, length))
    if len(solid.Solids) != 1 or not solid.isValid():
        raise Profiles.ProfileError(f"Extrusion of {profile.size} is not a single valid solid")
    return solid.Solids[0]
