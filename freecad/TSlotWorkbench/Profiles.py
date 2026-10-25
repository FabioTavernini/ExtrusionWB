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

   The ``B-Type`` family (Bosch Rexroth compatible) has real slot and bore
   dimensions, but every profile here has a solid core: the hollow chambers
   of a real profile, small fillets, and the shallow recess at each slot
   mouth are left out. Its geometry is right where parts meet the slot,
   but its cross-section area and mass are larger than the real profile's.

Extending the catalogue
-----------------------
Another family (I-Type, a specific manufacturer) is a set of
:func:`register_profile` calls with its own :class:`SlotDefinition`. As long
as the profile is a grid of square units with one slot per unit edge, no
geometry or GUI code needs to change.

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
B_TYPE_FAMILY = "B-Type"

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
    """A grid of square units, with a T-slot centred on every outer unit edge
    and a bore through the centre of every unit.

    ``size`` is the catalogue name (e.g. ``"4040"`` or ``"2040"``);
    ``outer`` is the edge length of one unit in mm. The grid is ``columns``
    units along local X by ``rows`` units along local Y, so a 2040 is one
    column by two rows. The profile is extruded along local Z.
    """

    family: str
    size: str
    outer: float
    slot: SlotDefinition
    bore_diameter: float
    columns: int = 1
    rows: int = 1

    def __post_init__(self):
        for name in ("family", "size"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ProfileError(f"Profile {name} must be a non-empty string, got {value!r}")
        _check_positive("Profile", "outer", self.outer)
        _check_positive("Profile", "bore_diameter", self.bore_diameter)
        for name in ("columns", "rows"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ProfileError(f"Profile {name} must be a whole number of at least 1, got {value!r}")
        if not isinstance(self.slot, SlotDefinition):
            raise ProfileError(f"Profile slot must be a SlotDefinition, got {self.slot!r}")

        label = f"Profile {self.family} {self.size}"
        for name, thickness in self.wall_thicknesses().items():
            if thickness < MIN_WALL:
                raise ProfileError(
                    f"{label}: {name} wall is {thickness:.3g} mm, below the {MIN_WALL} mm minimum"
                )

    @property
    def width(self):
        """Overall size along local X, in mm."""
        return self.outer * self.columns

    @property
    def height(self):
        """Overall size along local Y, in mm."""
        return self.outer * self.rows

    def wall_thicknesses(self):
        """Thinnest material between features, in mm, keyed by location.

        Every unit of the grid has the same features, so one unit is
        checked; two slots side by side on one face are ``2 * corner`` apart.
        Neighbouring slots round a corner are mirror images about the unit's
        diagonal, so the web between them is twice the distance from a slot's
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


# Grid layouts offered in every family, as (unit, columns, rows), in display
# order. They match the multi-unit profiles Rexroth makes in each series.
_LAYOUTS = (
    (20, 1, 1), (20, 1, 2), (20, 1, 3),
    (30, 1, 1), (30, 1, 2), (30, 1, 3),
    (40, 1, 1), (40, 1, 2), (40, 1, 3), (40, 2, 2),
)


def _register_family(family, units):
    """Register every layout of ``units``, a {unit: (slot, bore)} mapping."""
    for unit, columns, rows in _LAYOUTS:
        slot, bore = units[unit]
        size = f"{unit * columns}{unit * rows}"
        register_profile(ProfileDefinition(family, size, float(unit), slot, bore, columns, rows))


# Generic profiles: ILLUSTRATIVE dimensions only (see the module warning).
# The cavity tapers to the floor at 45 degrees, which gives a uniform web
# along each diagonal, as on typical commercial profiles.
_register_family(GENERIC_FAMILY, {
    20: (SlotDefinition(opening=6.0, lip=1.5, cavity_width=10.0, cavity_height=1.5,
                        floor_width=6.0, depth=5.0), 4.0),
    30: (SlotDefinition(opening=8.0, lip=2.0, cavity_width=14.0, cavity_height=2.5,
                        floor_width=9.0, depth=7.0), 6.0),
    40: (SlotDefinition(opening=8.0, lip=3.0, cavity_width=16.0, cavity_height=2.0,
                        floor_width=8.0, depth=9.0), 7.0),
})

# B-Type (Bosch Rexroth compatible): slots 6, 8 and 10. Slot and bore
# dimensions were measured from the cross-sections of Motedis' B-Type CAD
# models (which match Rexroth's published section areas to within 2%), and
# checked against the Rexroth Aluminum Framing catalogue (R999001283): its
# 20x20 drawing gives the 5.5 mm slot depth and the 5.5 mm bore. Fillets are
# replaced by sharp corners and the cavity tapers to the floor at 45 degrees,
# as on the real profiles. Multi-unit profiles reuse the unit's slot and bore.
_register_family(B_TYPE_FAMILY, {
    20: (SlotDefinition(opening=6.2, lip=1.5, cavity_width=12.0, cavity_height=1.44,
                        floor_width=6.88, depth=5.5), 5.5),
    30: (SlotDefinition(opening=8.0, lip=2.2, cavity_width=16.5, cavity_height=2.75,
                        floor_width=8.4, depth=9.0), 7.3),
    40: (SlotDefinition(opening=10.0, lip=6.0, cavity_width=20.1, cavity_height=2.536,
                        floor_width=12.172, depth=12.5), 10.0),
})
