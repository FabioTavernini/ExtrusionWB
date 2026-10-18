# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Profile catalogue for T-slot extrusions.

This module is the single place that knows *what* a profile is: plain
data, validated for internal consistency, importable without FreeCAD.
``Geometry.py`` turns a definition into a face and a solid, and
``Extrusion.py`` turns that into a document object.

.. warning::
   The ``Generic`` family uses illustrative dimensions. They give a
   recognisable T-slot section (four undercut slots and a centre bore), but
   they are not any manufacturer's specification, and must not be used to
   machine parts or choose slot hardware.

Extending the catalogue
-----------------------
Another family (B-Type, I-Type, a specific manufacturer) is a set of
:func:`register_profile` calls with its own :class:`SlotDefinition`. As long
as the profile is square with one slot per side, no geometry or GUI code
needs to change.

Slot coordinates
----------------
A slot is described in its own frame: ``u`` runs along the side of the
profile (0 at the slot centre line), ``v`` runs inwards from the outer face.
Going inwards, the slot is::

      v = 0         |<- opening ->|            outer face
      v = lip      _|             |_           lip (holds the T-nut)
                  |<--- cavity ---->|          straight cavity walls
      v = lip + cavity_height                  ...then a taper to
      v = depth       |<- floor ->|            the slot floor
"""

import math
from dataclasses import dataclass

GENERIC_FAMILY = "Generic"

DEFAULT_FAMILY = GENERIC_FAMILY
DEFAULT_SIZE = "4040"
DEFAULT_LENGTH = 750.0  # mm

# Thinnest wall the consistency checks accept between features (mm).
MIN_WALL = 1.0


class ProfileError(ValueError):
    """Raised for invalid profile definitions, lookups, or lengths."""


def _check_positive(owner, name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileError(f"{owner} {name} must be a number, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise ProfileError(f"{owner} {name} must be positive and finite, got {value!r}")


@dataclass(frozen=True)
class SlotDefinition:
    """Cross-section of one undercut T-slot, in mm (see the module docstring)."""

    opening: float        # width of the slot at the outer face
    lip: float            # thickness of the lips either side of the opening
    cavity_width: float   # width of the undercut cavity behind the lips
    cavity_height: float  # height of the cavity's straight side walls
    floor_width: float    # width of the slot floor
    depth: float          # distance from the outer face to the slot floor

    def __post_init__(self):
        for name in ("opening", "lip", "cavity_width", "cavity_height", "floor_width", "depth"):
            _check_positive("Slot", name, getattr(self, name))
        if self.cavity_width <= self.opening:
            raise ProfileError("Slot cavity must be wider than its opening (no undercut otherwise)")
        if self.floor_width > self.cavity_width:
            raise ProfileError("Slot floor must not be wider than the cavity")
        if self.lip + self.cavity_height >= self.depth:
            raise ProfileError("Slot lip plus cavity height must be less than the slot depth")

    @property
    def taper_start(self):
        """Depth ``v`` at which the cavity walls start tapering to the floor."""
        return self.lip + self.cavity_height


@dataclass(frozen=True)
class ProfileDefinition:
    """A square profile with the same T-slot on all four sides and a centre bore.

    ``size`` is the catalogue name (e.g. ``"4040"``); ``outer`` is the
    outer edge length in mm, measured along local X and Y. The profile is
    extruded along local Z.
    """

    family: str
    size: str
    outer: float
    slot: SlotDefinition
    bore_diameter: float

    def __post_init__(self):
        for name in ("family", "size"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ProfileError(f"Profile {name} must be a non-empty string, got {value!r}")
        _check_positive("Profile", "outer", self.outer)
        _check_positive("Profile", "bore_diameter", self.bore_diameter)
        if not isinstance(self.slot, SlotDefinition):
            raise ProfileError(f"Profile slot must be a SlotDefinition, got {self.slot!r}")

        label = f"Profile {self.family} {self.size}"
        for name, thickness in self.wall_thicknesses().items():
            if thickness < MIN_WALL:
                raise ProfileError(
                    f"{label}: {name} wall is {thickness:.3g} mm, below the {MIN_WALL} mm minimum"
                )

    def wall_thicknesses(self):
        """Thinnest material between features, in mm, keyed by location.

        Neighbouring slots are mirror images about the profile's diagonal,
        so the web between them is twice the distance from a slot's
        outermost cavity corners to that diagonal.
        """
        half = self.outer / 2.0
        s = self.slot
        cavity_corner = (s.cavity_width / 2.0, half - s.taper_start)
        floor_corner = (s.floor_width / 2.0, half - s.depth)
        return {
            "corner": half - s.cavity_width / 2.0,             # beside the cavity, to the next face
            "diagonal web": math.sqrt(2.0) * min(y - x for x, y in (cavity_corner, floor_corner)),
            "core": half - s.depth - self.bore_diameter / 2.0,  # slot floor to bore
            "lip": s.lip,
        }


# Keyed by (family, size). Insertion order is the display order.
_CATALOGUE = {}


def register_profile(profile):
    """Add a profile to the catalogue. Duplicate (family, size) is an error."""
    if not isinstance(profile, ProfileDefinition):
        raise ProfileError(f"Expected a ProfileDefinition, got {type(profile).__name__}")
    key = (profile.family, profile.size)
    if key in _CATALOGUE:
        raise ProfileError(f"Profile {profile.family} {profile.size} is already registered")
    _CATALOGUE[key] = profile
    return profile


def families():
    """Return the registered family names, in registration order."""
    return list(dict.fromkeys(family for family, _ in _CATALOGUE))


def sizes(family=DEFAULT_FAMILY):
    """Return the size names registered for ``family``, in registration order."""
    result = [size for fam, size in _CATALOGUE if fam == family]
    if not result:
        raise ProfileError(f"Unknown profile family {family!r}")
    return result


def get_profile(family, size):
    """Look up a profile, raising :class:`ProfileError` if it does not exist."""
    try:
        return _CATALOGUE[(family, size)]
    except KeyError:
        raise ProfileError(f"Unknown profile {family!r} {size!r}") from None


def validate_length(length):
    """Return ``length`` as a float, or raise if it is not a positive finite number."""
    if isinstance(length, bool):
        raise ProfileError(f"Length must be a number, got {length!r}")
    try:
        value = float(length)
    except (TypeError, ValueError):
        raise ProfileError(f"Length must be a number, got {length!r}") from None
    if not math.isfinite(value) or value <= 0:
        raise ProfileError(f"Length must be positive, got {length!r}")
    return value


# Generic profiles: ILLUSTRATIVE dimensions only (see the module warning).
# The cavity tapers to the floor at 45 degrees, which gives a uniform web
# along each diagonal, as on typical commercial profiles.
for _size, _outer, _slot, _bore in (
    ("2020", 20.0, SlotDefinition(opening=6.0, lip=1.5, cavity_width=10.0, cavity_height=1.5,
                                  floor_width=6.0, depth=5.0), 4.0),
    ("3030", 30.0, SlotDefinition(opening=8.0, lip=2.0, cavity_width=14.0, cavity_height=2.5,
                                  floor_width=9.0, depth=7.0), 6.0),
    ("4040", 40.0, SlotDefinition(opening=8.0, lip=3.0, cavity_width=16.0, cavity_height=2.0,
                                  floor_width=8.0, depth=9.0), 7.0),
):
    register_profile(ProfileDefinition(GENERIC_FAMILY, _size, _outer, _slot, _bore))
del _size, _outer, _slot, _bore
