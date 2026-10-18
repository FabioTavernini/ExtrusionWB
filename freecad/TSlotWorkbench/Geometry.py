# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Cross-section and solid construction for T-slot profiles.

The cross-section is built directly as one face, with no Booleans between
solids:

1. :func:`outline_points` traces the outer boundary as a single closed
   polygon. It walks the four sides clockwise, and each side contributes
   its T-slot recess (opening, undercut cavity, taper, floor).
2. The centre bore is a circle, used as the face's inner wire.
3. The face is extruded along +Z into one solid.

The section is centred on the local Z axis and the solid runs from Z = 0
to Z = length.
"""

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
    half = profile.outer / 2.0
    # The top side, from the top-left corner towards +X: (u, v) -> (u, half - v).
    top = [(-half, half)] + [(u, half - v) for u, v in slot_points(profile.slot)]
    points = []
    for _ in range(4):
        points.extend(top)
        # Rotate -90 degrees about Z to get the next side, clockwise.
        top = [(y, -x) for x, y in top]
    return points


def create_profile_face(profile):
    """Return the cross-section of ``profile`` as a valid ``Part.Face`` in the XY plane."""
    outer = Part.makePolygon([FreeCAD.Vector(x, y, 0.0) for x, y in outline_points(profile)], True)
    bore = Part.Wire(Part.makeCircle(profile.bore_diameter / 2.0))
    face = Part.makeFace([outer, bore], "Part::FaceMakerBullseye")
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
    length = Profiles.validate_length(length)
    solid = create_profile_face(profile).extrude(FreeCAD.Vector(0.0, 0.0, length))
    if len(solid.Solids) != 1 or not solid.isValid():
        raise Profiles.ProfileError(f"Extrusion of {profile.size} is not a single valid solid")
    return solid.Solids[0]
