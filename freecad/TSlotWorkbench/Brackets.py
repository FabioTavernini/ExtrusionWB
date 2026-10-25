# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Catalogue of 90 degree corner brackets (gussets).

Plain data, like ``Profiles``: importable without FreeCAD. ``CornerBracket``
turns a definition into a shape and places it at a joint.

A bracket is described in its own frame. Its two legs meet along the
local X axis (the corner line), and the bracket is centred on X = 0::

      z
      |__
      |  |  leg on the post: y in [0, wall], z in [0, leg]
      |  |\\
      |  | \\    closed triangular cheeks at both ends of the width
      |  |__\\_____
      |__________|___ y   leg on the base: z in [0, wall], y in [0, leg]

Each leg has a slotted bolt hole on the centre line, running along the leg
from ``hole_start`` to ``hole_start + hole_length``, measured from the
corner. The cheeks are ``wall`` thick.

Dimensions follow Rexroth's die-cast gussets (Aluminum Framing catalogue,
section 3): leg length, width, wall thickness, the bolt slot's width,
length and position, and the screw in the fastener kit. The cheek thickness is not given there, so the wall
thickness is used. The ribs, centring lugs and fillets are left out.
"""

import math
from dataclasses import dataclass

from .Profiles import ProfileError


@dataclass(frozen=True)
class BracketDefinition:
    """One corner bracket size, dimensions in mm (see the module docstring)."""

    size: str           # catalogue name; the profile series it fits ("20", "30", "40")
    series: float       # unit edge of the profiles it fits
    leg: float          # length of each leg from the corner
    width: float        # size across, along the corner line
    wall: float         # thickness of legs and cheeks
    hole_width: float   # width of the bolt slot
    hole_length: float  # length of the bolt slot along the leg, end to end
    hole_start: float   # distance from the corner to the start of the slot
    screw: str = "M4"   # thread of the kit's screws
    screw_length: float = 8.0  # length of the kit's screws

    def __post_init__(self):
        for name in ("size", "screw"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ProfileError(f"Bracket {name} must be a non-empty string, got {value!r}")
        for name in ("series", "leg", "width", "wall", "hole_width", "hole_length", "hole_start",
                     "screw_length"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProfileError(f"Bracket {name} must be a number, got {value!r}")
            if not math.isfinite(value) or value <= 0:
                raise ProfileError(f"Bracket {name} must be positive and finite, got {value!r}")
        label = f"Bracket {self.size}"
        if self.wall >= self.leg:
            raise ProfileError(f"{label}: wall must be thinner than the leg is long")
        if self.hole_length < self.hole_width:
            raise ProfileError(f"{label}: bolt slot must be at least as long as it is wide")
        if self.hole_start < self.wall:
            raise ProfileError(f"{label}: bolt slot must start clear of the other leg")
        if self.hole_end >= self.leg:
            raise ProfileError(f"{label}: bolt slot must end before the end of the leg")
        if self.hole_width >= self.width - 2.0 * self.wall:
            raise ProfileError(f"{label}: bolt slot must fit between the cheeks")

    @property
    def hole_end(self):
        """Distance from the corner to the end of the bolt slot."""
        return self.hole_start + self.hole_length


# Keyed by size. Insertion order is the display order.
_CATALOGUE = {}


def register_bracket(bracket):
    """Add a bracket to the catalogue. A duplicate size is an error."""
    if not isinstance(bracket, BracketDefinition):
        raise ProfileError(f"Expected a BracketDefinition, got {type(bracket).__name__}")
    if bracket.size in _CATALOGUE:
        raise ProfileError(f"Bracket {bracket.size} is already registered")
    _CATALOGUE[bracket.size] = bracket
    return bracket


def sizes():
    """Return the registered bracket sizes, in registration order."""
    return list(_CATALOGUE)


def get_bracket(size):
    """Look up a bracket, raising :class:`ProfileError` if it does not exist."""
    try:
        return _CATALOGUE[size]
    except KeyError:
        raise ProfileError(f"Unknown bracket size {size!r}") from None


def bracket_for(unit):
    """The largest bracket whose series fits profiles with ``unit`` mm units."""
    fitting = [b for b in _CATALOGUE.values() if b.series <= unit + 1e-9]
    if not fitting:
        raise ProfileError(f"No corner bracket fits {unit:g} mm profiles")
    return max(fitting, key=lambda b: b.series)


# Rexroth gussets 20x20 (3 842 523 508), 30x30 (3 842 523 525) and
# 40x40 (3 842 528 967). The bolt slot is given as its length and the
# distance from the corner to its far end. Screws are those of the kits
# with fasteners: M4x8, M6x14, and M8 for the 40 (a 14 mm T-bolt there;
# M8x16 here).
for _b in (
    BracketDefinition("20", 20.0, leg=18.0, width=18.0, wall=3.0,
                      hole_width=4.5, hole_length=7.0, hole_start=14.7 - 7.0, screw="M4", screw_length=8.0),
    BracketDefinition("30", 30.0, leg=27.0, width=28.0, wall=6.0,
                      hole_width=6.4, hole_length=10.0, hole_start=20.0 - 10.0, screw="M6", screw_length=14.0),
    BracketDefinition("40", 40.0, leg=36.0, width=38.0, wall=5.5,
                      hole_width=8.7, hole_length=20.0, hole_start=29.5 - 20.0, screw="M8", screw_length=16.0),
):
    register_bracket(_b)
del _b
