# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Catalogue of mounting hardware: angle brackets for fixing a plate, and adjustable feet.

Plain data, like ``Brackets``: importable without FreeCAD. ``Mounting``
turns a definition into a shape and places it.

An angle bracket has two legs. Leg A lies on a side face of the extrusion,
with a slotted bolt hole over the T-slot. Leg B is the ledge: it stands out
of the face at the bend, with holes for the screws into the plate. The
dimensions are typical of the 20, 30 and 40 series angle brackets, not any
one maker's.

A foot is a threaded stud screwed into the bore at the end of an extrusion,
with a pad on its end.
"""

import math
from dataclasses import dataclass

from .Profiles import ProfileError


def _check_positive(owner, definition, names):
    for name in names:
        value = getattr(definition, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProfileError(f"{owner} {name} must be a number, got {value!r}")
        if not math.isfinite(value) or value <= 0:
            raise ProfileError(f"{owner} {name} must be positive and finite, got {value!r}")


@dataclass(frozen=True)
class AngleBracketDefinition:
    """One angle bracket size, dimensions in mm."""

    size: str            # catalogue name; the profile series it fits ("20", "30", "40")
    series: float        # unit edge of the profiles it fits
    width: float         # size along the extrusion
    leg: float           # length of leg A, on the face, across the slot
    reach: float         # how far leg B stands out of the face
    wall: float          # thickness of both legs
    hole_width: float    # width of the bolt slot in leg A
    hole_length: float   # length of the bolt slot, along the extrusion
    plate_hole: float    # diameter of the holes in leg B
    screw: str = "M4"    # thread of the bolt
    screw_length: float = 8.0

    def __post_init__(self):
        if not isinstance(self.size, str) or not self.size.strip():
            raise ProfileError(f"Angle bracket size must be a non-empty string, got {self.size!r}")
        _check_positive(f"Angle bracket {self.size}", self, (
            "series", "width", "leg", "reach", "wall", "hole_width", "hole_length", "plate_hole", "screw_length"))
        label = f"Angle bracket {self.size}"
        if self.wall >= min(self.leg, self.reach) / 2.0:
            raise ProfileError(f"{label}: wall must be much thinner than the legs")
        if self.hole_length < self.hole_width:
            raise ProfileError(f"{label}: bolt slot must be at least as long as it is wide")
        if self.hole_length >= self.width:
            raise ProfileError(f"{label}: bolt slot must be shorter than the bracket is wide")
        if self.hole_width >= self.leg / 2.0:
            raise ProfileError(f"{label}: bolt slot is too wide for leg A")
        if self.plate_hole * 2.0 >= self.width:
            raise ProfileError(f"{label}: two plate holes do not fit the width")
        if self.plate_hole >= self.reach - self.wall:
            raise ProfileError(f"{label}: plate hole does not fit leg B")


@dataclass(frozen=True)
class FootDefinition:
    """One adjustable foot, dimensions in mm."""

    thread: str          # "M8"
    nominal: float       # nominal diameter of the stud
    pad_diameter: float
    pad_thickness: float
    engage: float        # length of the stud inside the extrusion's bore

    def __post_init__(self):
        if not isinstance(self.thread, str) or not self.thread.strip():
            raise ProfileError(f"Foot thread must be a non-empty string, got {self.thread!r}")
        _check_positive(f"Foot {self.thread}", self, ("nominal", "pad_diameter", "pad_thickness", "engage"))
        if self.pad_diameter <= self.nominal:
            raise ProfileError(f"Foot {self.thread}: the pad must be wider than the stud")


DEFAULT_EXTENSION = 30.0  # mm from the extrusion's end to the pad

_ANGLE_BRACKETS = {}
_FEET = {}


def register_angle_bracket(bracket):
    if not isinstance(bracket, AngleBracketDefinition):
        raise ProfileError(f"Expected an AngleBracketDefinition, got {type(bracket).__name__}")
    if bracket.size in _ANGLE_BRACKETS:
        raise ProfileError(f"Angle bracket {bracket.size} is already registered")
    _ANGLE_BRACKETS[bracket.size] = bracket
    return bracket


def register_foot(foot):
    if not isinstance(foot, FootDefinition):
        raise ProfileError(f"Expected a FootDefinition, got {type(foot).__name__}")
    if foot.thread in _FEET:
        raise ProfileError(f"Foot {foot.thread} is already registered")
    _FEET[foot.thread] = foot
    return foot


def angle_bracket_sizes():
    return list(_ANGLE_BRACKETS)


def get_angle_bracket(size):
    try:
        return _ANGLE_BRACKETS[size]
    except KeyError:
        raise ProfileError(f"Unknown angle bracket size {size!r}") from None


def angle_bracket_for(unit):
    """The largest angle bracket whose series fits profiles with ``unit`` mm units."""
    fitting = [b for b in _ANGLE_BRACKETS.values() if b.series <= unit + 1e-9]
    if not fitting:
        raise ProfileError(f"No angle bracket fits {unit:g} mm profiles")
    return max(fitting, key=lambda b: b.series)


def foot_threads():
    return list(_FEET)


def get_foot(thread):
    try:
        return _FEET[thread]
    except KeyError:
        raise ProfileError(f"Unknown foot thread {thread!r}") from None


def foot_for(unit):
    """The default foot thread for profiles with ``unit`` mm units: M5 for 20, M6 for 30, M8 for 40 and up."""
    return "M5" if unit < 30 else "M6" if unit < 40 else "M8"


for _b in (
    AngleBracketDefinition("20", 20.0, width=20.0, leg=20.0, reach=18.0, wall=3.0, hole_width=4.5,
                           hole_length=8.0, plate_hole=3.5, screw="M4", screw_length=8.0),
    AngleBracketDefinition("30", 30.0, width=30.0, leg=30.0, reach=25.0, wall=4.0, hole_width=6.4,
                           hole_length=12.0, plate_hole=4.5, screw="M6", screw_length=14.0),
    AngleBracketDefinition("40", 40.0, width=40.0, leg=40.0, reach=30.0, wall=5.0, hole_width=8.7,
                           hole_length=16.0, plate_hole=5.5, screw="M8", screw_length=16.0),
):
    register_angle_bracket(_b)
for _f in (
    FootDefinition("M5", 5.0, pad_diameter=25.0, pad_thickness=6.0, engage=12.0),
    FootDefinition("M6", 6.0, pad_diameter=30.0, pad_thickness=7.0, engage=14.0),
    FootDefinition("M8", 8.0, pad_diameter=40.0, pad_thickness=8.0, engage=18.0),
    FootDefinition("M10", 10.0, pad_diameter=50.0, pad_thickness=9.0, engage=22.0),
):
    register_foot(_f)
del _b, _f
