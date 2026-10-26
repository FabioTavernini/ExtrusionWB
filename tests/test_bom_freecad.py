# SPDX-License-Identifier: LGPL-2.1-or-later
"""Bill of materials tests that need a real FreeCAD (run with tools/run_tests.sh)."""

import csv
import io
import unittest

try:
    import FreeCAD
except ImportError:
    FreeCAD = None

if FreeCAD is not None:
    from freecad.TSlotWorkbench import Bom, Extrusion, Frame, Hardware, Mounting


@unittest.skipIf(FreeCAD is None, "FreeCAD is not available")
class TestBom(unittest.TestCase):

    def setUp(self):
        self.doc = FreeCAD.newDocument("TSlotBomTest")

    def tearDown(self):
        for name in list(FreeCAD.listDocuments()):
            FreeCAD.closeDocument(name)

    def counts(self, rows):
        return {(r.category, r.item, r.length): r.quantity for r in rows}

    def test_frame(self):
        Frame.make_rectangular_frame(self.doc, 800, 400, family="B-Type", hardware=True)
        self.doc.recompute()
        rows = Bom.collect(self.doc.Objects)
        counts = self.counts(rows)
        self.assertEqual(counts[("Extrusion", "B-Type 4040", 800.0)], 2)
        self.assertEqual(counts[("Extrusion", "B-Type 4040", 320.0)], 2)
        self.assertEqual(counts[("Corner bracket", "40 corner bracket", None)], 4)
        nuts = {k: v for k, v in counts.items() if k[0] == "T-nut"}
        self.assertEqual(sum(nuts.values()), 8)
        self.assertEqual(list(nuts)[0][1], "M8 T-nut, 10 mm slot")
        if Hardware.fasteners_available():
            screws = {k: v for k, v in counts.items() if k[0] == "Screw"}
            self.assertEqual(sum(screws.values()), 8)
        self.assertEqual(Bom.stock_totals(rows), {"B-Type 4040": 2 * 800 + 2 * 320})
        self.assertEqual([r.category for r in rows][:2], ["Extrusion", "Extrusion"])
        self.assertEqual(rows[0].length, 800.0)  # longest first

    def test_mounting_parts(self):
        ext = Extrusion.make_extrusion(self.doc, length=500)
        bracket = Mounting.make_angle_bracket(self.doc, ext, "+Y", 0, 100.0)
        Mounting.make_angle_bracket_hardware(self.doc, bracket)
        Mounting.make_feet(self.doc, ext, "End")
        self.doc.recompute()
        counts = self.counts(Bom.collect(self.doc.Objects))
        self.assertEqual(counts[("Angle bracket", "40 angle bracket", None)], 1)
        self.assertEqual(counts[("Foot", "M8 adjustable foot", None)], 1)

    def test_selection_brings_what_is_attached(self):
        group = Frame.make_rectangular_frame(self.doc, 800, 400, hardware=False)
        lone = Extrusion.make_extrusion(self.doc, length=100)
        self.doc.recompute()
        everything = Bom.collect(self.doc.Objects)
        in_group = Bom.collect([group])
        self.assertEqual(sum(r.quantity for r in in_group), sum(r.quantity for r in everything) - 1)
        one = Bom.collect([next(o for o in group.Group if getattr(o, "Length", None) is not None
                                and o.Length.Value == 800.0)])
        counts = self.counts(one)
        self.assertEqual(counts[("Extrusion", "Generic 4040", 800.0)], 1)
        self.assertEqual(counts[("Corner bracket", "40 corner bracket", None)], 2)  # its two joints
        self.assertNotIn(lone.Name, [o.Name for o in Bom.expand([group])])

    def test_csv_text_and_sheet(self):
        Frame.make_rectangular_frame(self.doc, 800, 400, hardware=False)
        self.doc.recompute()
        rows = Bom.collect(self.doc.Objects)
        parsed = list(csv.reader(io.StringIO(Bom.to_csv(rows))))
        self.assertEqual(tuple(parsed[0]), Bom.HEADER)
        self.assertEqual(parsed[1], ["Extrusion", "Generic 4040", "800", "2", "1600"])
        self.assertEqual(parsed[-1][0], "Corner bracket")
        self.assertEqual(parsed[-1][2:], ["", "4", ""])
        text = Bom.to_text(rows)
        self.assertIn("Total Generic 4040: 2.240 m", text)
        sheet = Bom.to_sheet(self.doc, rows)
        self.doc.recompute()
        self.assertEqual(sheet.getContents("A1"), "'Category")  # FreeCAD marks text with a quote
        self.assertEqual(sheet.getContents("B2"), "'Generic 4040")
        self.assertEqual(sheet.get("D2"), 2)

    def test_empty(self):
        self.assertEqual(Bom.collect(self.doc.Objects), [])
        self.assertEqual(Bom.collect([self.doc.addObject("App::DocumentObjectGroup", "G")]), [])
