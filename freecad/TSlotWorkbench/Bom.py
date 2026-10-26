# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileNotice: Part of the TSlotWorkbench addon.

"""Bill of materials and cut list.

:func:`collect` counts the parts of a document, or of the selected parts and
everything attached to them, into :class:`Row` tuples; :func:`to_csv` and
:func:`to_sheet` write them out. Parts are grouped when they are the same
purchase: extrusions by profile and length, brackets by size, T-nuts by
thread and slot, screws by type, size and length, feet by thread.
"""

import csv
import io
from collections import namedtuple

import FreeCAD

from . import CornerBracket, Hardware, Mounting
from .Extrusion import Extrusion

Row = namedtuple("Row", "category item length quantity")
Row.__doc__ = """One line of the list. ``length`` is in mm for extrusions and None for the rest."""

HEADER = ("Category", "Item", "Length (mm)", "Quantity", "Total length (mm)")

# Display order of the categories.
CATEGORIES = ("Extrusion", "Corner bracket", "Angle bracket", "Foot", "T-nut", "Screw")


def expand(objects):
    """``objects`` with the contents of groups, and what is attached to the extrusions, added.

    Duplicates are dropped; the order is kept.
    """
    seen, out = set(), []

    def add(obj):
        key = (obj.Document.Name, obj.Name)
        if key in seen:
            return
        seen.add(key)
        out.append(obj)
        for child in getattr(obj, "Group", None) or ():
            add(child)
        if isinstance(getattr(obj, "Proxy", None), Extrusion):
            for group in CornerBracket.attached_to([obj]):
                for item in group:
                    add(item)

    for obj in objects:
        add(obj)
    return out


def _number(value):
    return float(getattr(value, "Value", value))


def collect(objects):
    """The bill of materials of ``objects`` (see :func:`expand`), as a sorted list of rows."""
    counts = {}

    def count(category, item, length=None):
        key = (category, item, None if length is None else round(length, 2))
        counts[key] = counts.get(key, 0) + 1

    for obj in expand(objects):
        proxy = getattr(obj, "Proxy", None)
        if isinstance(proxy, Extrusion):
            count("Extrusion", f"{obj.ProfileFamily} {obj.ProfileSize}", obj.Length.Value)
        elif isinstance(proxy, CornerBracket.CornerBracket):
            count("Corner bracket", f"{obj.BracketSize} corner bracket")
        elif isinstance(proxy, Mounting.AngleBracket):
            count("Angle bracket", f"{obj.BracketSize} angle bracket")
        elif isinstance(proxy, Mounting.Foot):
            count("Foot", f"{obj.Thread} adjustable foot")
        elif isinstance(proxy, Hardware.TSlotNut):
            opening = Hardware._profile(obj.Profile).slot.opening if obj.Profile is not None else 0.0
            count("T-nut", f"{obj.Thread} T-nut, {opening:g} mm slot")
        elif Hardware.is_screw(obj):
            length = _number(obj.Length) if hasattr(obj, "Length") else 0.0
            count("Screw", f"{obj.Type} {obj.Diameter} x {length:g}")

    order = {name: i for i, name in enumerate(CATEGORIES)}
    rows = [Row(c, item, length, n) for (c, item, length), n in counts.items()]
    return sorted(rows, key=lambda r: (order[r.category], r.item, -(r.length or 0.0)))


def total_length(row):
    return None if row.length is None else row.length * row.quantity


def stock_totals(rows):
    """Total extrusion length needed per profile, as {profile: mm}."""
    totals = {}
    for row in rows:
        if row.category == "Extrusion":
            totals[row.item] = totals.get(row.item, 0.0) + total_length(row)
    return totals


def _cells(row):
    total = total_length(row)
    return (row.category, row.item, "" if row.length is None else f"{row.length:g}", row.quantity,
            "" if total is None else f"{total:g}")


def to_csv(rows):
    """The list as CSV text, with a header line."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow(_cells(row))
    return out.getvalue()


def to_text(rows):
    """The list as aligned plain text, with the stock needed per profile at the end."""
    table = [HEADER] + [tuple(str(c) for c in _cells(r)) for r in rows]
    widths = [max(len(line[i]) for line in table) for i in range(len(HEADER))]
    lines = ["  ".join(cell.ljust(w) if i < 2 else cell.rjust(w) for i, (cell, w) in enumerate(zip(line, widths)))
             for line in table]
    lines.insert(1, "  ".join("-" * w for w in widths))
    totals = stock_totals(rows)
    if totals:
        lines.append("")
        lines.extend(f"Total {profile}: {mm / 1000.0:.3f} m" for profile, mm in sorted(totals.items()))
    return "\n".join(lines)


def to_sheet(doc, rows, name="BOM"):
    """Write the list to a new spreadsheet in ``doc`` and return it. The caller recomputes."""
    sheet = doc.addObject("Spreadsheet::Sheet", name)
    sheet.Label = "Bill of materials"
    for col, title in enumerate(HEADER):
        sheet.set(f"{chr(65 + col)}1", title)
        sheet.setStyle(f"{chr(65 + col)}1", "bold")
    for r, row in enumerate(rows, start=2):
        total = total_length(row)
        sheet.set(f"A{r}", row.category)
        sheet.set(f"B{r}", row.item)
        if row.length is not None:
            sheet.set(f"C{r}", f"{row.length:g}")
            sheet.set(f"E{r}", f"{total:g}")
        sheet.set(f"D{r}", str(row.quantity))
    return sheet
