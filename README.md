# TSlotWorkbench

A FreeCAD workbench for creating parametric metric T-slot aluminium
extrusions: pick a profile size and a length, and edit both later in
FreeCAD's property editor.

> [!WARNING]
> **The `Generic` profiles use illustrative dimensions, not a manufacturer's.**
> They have the right outer size and a recognisable T-slot section (four
> undercut slots and a centre bore), but the slot, lip and bore dimensions
> are not any vendor's specification, and the corners are solid where real
> profiles are often hollow. Use them for layout, lengths and visualisation,
> **not** for machining, mass or stiffness, or to choose T-nuts and fasteners.
>
> The **`B-Type`** profiles (Bosch Rexroth compatible) have real slot and
> bore dimensions, so the slots match B-Type T-nuts and connectors. Their
> core is still solid, though, so area and mass are too high (see
> [B-Type](#b-type-bosch-rexroth-compatible)).

## Features

- **Extrusions** workbench with a **T-Slot** toolbar and an **Extrusions** menu.
- **Create Extrusion** command: adds a 4040 × 750 mm extrusion, creating a
  document if none is open. The command is one undo step.
- **Create 2020 / 3030 / 4040 Extrusion** quick-insert buttons next to it,
  which add a 750 mm extrusion of that size directly.
- Parametric `Part::FeaturePython` object with these properties:

  | Property           | Type        | Notes                                   |
  |--------------------|-------------|-----------------------------------------|
  | `ProfileFamily`    | Enumeration | `Generic` (default) or `B-Type`         |
  | `ProfileSize`      | Enumeration | `2020`, `2040`, `2060`, `3030`, `3060`, `3090`, `4040` (default), `4080`, `40120`, `8080` |
  | `Length`           | Length      | Default 750 mm; must be > 0             |
  | `CrossSectionArea` | Area        | Read-only; area of the generated section |

- Geometry: a T-slot cross-section (see [Cross-section](#cross-section)),
  centred on the object's local Z axis. The extrusion
  runs from Z = 0 to Z = `Length`. Moving or rotating the
  object (its `Placement`) is kept when the size or length changes.
- The tree label follows the profile, e.g. `Extrusion 4040 x 750 mm`.
  Rename the object and the label is never overwritten again.
- Documents save and reopen normally. The object stays editable.
- Documents saved by v0.1 (rectangular blocks) are upgraded when opened:
  each extrusion is rebuilt with the T-slot section, keeping its size,
  length, placement and label.

## Cross-section

Each `Generic` 2020, 3030 or 4040 profile is square, with the same undercut
T-slot on all four sides and a round bore through the centre. Going inwards from an outer face,
a slot has a narrow **opening** between two **lips**, then a wider **cavity**
(where a T-nut sits), whose walls taper at 45° to the **floor**:

| Parameter (mm)        | 2020 | 3030 | 4040 |
|-----------------------|-----:|-----:|-----:|
| Outer size            | 20   | 30   | 40   |
| Slot opening          | 6    | 8    | 8    |
| Lip thickness         | 1.5  | 2    | 3    |
| Cavity width          | 10   | 14   | 16   |
| Cavity straight walls | 1.5  | 2.5  | 2    |
| Slot floor width      | 6    | 9    | 8    |
| Slot depth            | 5    | 7    | 9    |
| Centre bore diameter  | 4    | 6    | 7    |
| Section area (mm²)    | 227.4 | 552.7 | 1145.5 |

These numbers are illustrative only. When a profile is defined, its
dimensions are checked for consistency: the cavity must be wider than the
opening, and every wall (lips, corners, the diagonal webs between
neighbouring slots, and the core between slot floors and bore) must be at
least 1 mm thick.

How it is built (`Geometry.py`): the outer boundary is traced as **one
closed polygon**, walking the four sides with a slot recess in each. The
bore is a circle used as the face's inner wire. That face is extruded along
+Z. No Booleans are used, and the result is one valid, closed solid with a
single shell.

## Supported FreeCAD versions

Tested on **FreeCAD 1.1.4** (Flathub flatpak, Linux, Python 3.13), both
headless and in the GUI. `package.xml` declares `<freecadmin>1.1.0</freecadmin>`.
Older versions may work, since the addon only uses long-standing APIs, but
they have not been tested.

## Installation (development)

The addon uses the modern namespaced layout from the
[FreeCAD Addon Academy](https://freecad.github.io/Addon-Academy/): code
lives in `freecad/TSlotWorkbench/` and FreeCAD discovers it through the
`package.xml` at the repository root. There are no third-party dependencies.

Symlink the checkout into your FreeCAD **user Mod directory**. To find that
directory, run this in FreeCAD's Python console:

```python
import FreeCAD, os; print(os.path.join(FreeCAD.getUserAppDataDir(), "Mod"))
```

Typical locations for FreeCAD 1.1:

| Install            | User Mod directory                                              |
|--------------------|-----------------------------------------------------------------|
| Linux              | `~/.local/share/FreeCAD/v1-1/Mod/`                              |
| Linux, flatpak     | `~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/`         |
| macOS              | `~/Library/Application Support/FreeCAD/v1-1/Mod/`              |
| Windows            | `%APPDATA%\FreeCAD\v1-1\Mod\`                                   |

```shell
MOD="$HOME/.local/share/FreeCAD/v1-1/Mod"        # adjust, see above
mkdir -p "$MOD"
ln -s "$(pwd)" "$MOD/TSlotWorkbench"
```

On Windows, use `mklink /D "%APPDATA%\FreeCAD\v1-1\Mod\TSlotWorkbench" C:\path\to\checkout`
from an elevated prompt, or with Developer Mode enabled.

The flatpak build can follow a symlink only if it can read the target. Its
default permissions cover your home directory. If the checkout is elsewhere,
grant access, for example with
`flatpak override --user --filesystem=/path/to/checkout org.freecad.FreeCAD`.

Restart FreeCAD after installing. FreeCAD scans `Mod/` only at startup, and
most code changes also need a restart.

To uninstall, remove the symlink and restart FreeCAD.

## Usage

1. Choose **Extrusions** in the workbench selector.
2. Click **Create Extrusion** on the toolbar, or use **Extrusions → Create Extrusion**.
   A 40 × 40 × 750 mm extrusion appears and is selected. The **2020**,
   **3030** and **4040** buttons next to it insert that size directly.
3. In the property editor, change `ProfileSize` (for example to `3030`) and
   `Length` (for example to `1200 mm`). The geometry is rebuilt on the next
   recompute. FreeCAD usually recomputes right after a property edit; if the
   object shows as touched instead, press **Refresh** (Ctrl+R).
4. Position the extrusion with its `Placement`, or with **Edit → Placement…**.
5. Save, close and reopen the document. The extrusion is still editable.

Scripted use, in FreeCAD's Python console:

```python
import FreeCAD
from freecad.TSlotWorkbench.Extrusion import make_extrusion

doc = FreeCAD.ActiveDocument or FreeCAD.newDocument()
bar = make_extrusion(doc, size="2020", length=500)
doc.recompute()
```

## Running the tests

```shell
tools/run_tests.sh          # pure-Python tests + headless FreeCAD tests
tools/run_tests.sh --gui    # ... plus a GUI smoke test (offscreen, no display needed)
```

The script runs three stages:

1. **Pure Python** (`python3 -m unittest discover -s tests`). `tests/test_profiles.py`
   covers the profile catalogue, lookups, slot and wall consistency checks,
   invalid definitions and length validation. Tests that need FreeCAD are reported as *skipped* here, not
   faked.
2. **Headless FreeCAD** (`FreeCADCmd tools/freecad_test_runner.py`). Runs the
   whole `tests/` directory inside FreeCAD:
   - `tests/test_geometry_freecad.py` probes the actual shape: valid single
     closed solid (including a full BOP check); outer size and length; on
     every side, a line section through the opening and one through the
     cavity, proving each slot is undercut; the bore runs through the full
     length; four-fold symmetry; the sizes differ; regeneration is repeatable.
   - `tests/test_extrusion_freecad.py` covers the document object: section
     area and volume against a hand calculation, recompute after edits,
     placement preservation, labels, the error state for zero length, undo,
     save/reopen/edit, and upgrading `tests/fixtures/mvp_v0_1.FCStd`, a
     real document saved by v0.1.
3. **GUI smoke test** (`FreeCAD tools/gui_smoke_test.py`, `--gui` only). Starts
   the real FreeCAD GUI with `QT_QPA_PLATFORM=offscreen`, activates the
   workbench, checks its toolbar, menu and command, runs **Create Extrusion**
   with and without an open document, undoes it, saves and reopens a
   document, and opens the v0.1 fixture.

FreeCAD stages run against a temporary user-data and temp directory whose
`Mod/` holds a symlink to the checkout, so FreeCAD finds the addon the same
way it finds a real install, and your FreeCAD settings are left alone. The
script uses `FreeCADCmd`/`FreeCAD` on `PATH`, then the Flathub flatpak. To
use a specific build, set `FREECAD_BIN_DIR=/path/to/freecad/bin`.

`test_zero_length_marks_error` intentionally prints a `ProfileError`
traceback; that is FreeCAD reporting the expected recompute error.

The offscreen GUI run has no OpenGL, so it does not test 3D rendering. Check
the visual result by hand in a normal FreeCAD session.

## Project layout

```text
package.xml                     FreeCAD addon manifest
pyproject.toml                  Python project metadata (dev tooling only)
Resources/Icons/                Workbench and command icons
freecad/TSlotWorkbench/
    __init__.py                 Package marker and resource paths (no FreeCAD import)
    init_gui.py                 Workbench definition and registration
    Commands.py                 TSlot_CreateExtrusion GUI command
    Extrusion.py                Part::FeaturePython proxy and make_extrusion()
    Profiles.py                 Profile and slot dimensions (pure Python, no FreeCAD)
    Geometry.py                 Cross-section face and extruded solid
tests/                          unittest suites (pure Python and FreeCAD)
tests/fixtures/                 Documents saved by older versions
tools/                          Test runners
```

`Profiles.py` holds data only: a `ProfileDefinition` (outer size, bore,
and a `SlotDefinition`) per size. A new family of square, one-slot-per-side
profiles, such as B-Type or I-Type, is a set of `register_profile(...)`
calls, with no changes to geometry or GUI code. `Geometry.py` turns a
definition into a face (`create_profile_face`) and a solid
(`create_extrusion_shape`).

The proxy class is stored in documents as
`freecad.TSlotWorkbench.Extrusion.Extrusion`. **Do not rename or move it**
without leaving a compatibility alias, or saved files will no longer load.
On reopen, `onDocumentRestored` refreshes the enumeration choices from the
current catalogue, so old documents pick up newly added sizes. A hidden
`SchemaVersion` property records the object version. Objects without it
(v0.1) get it added and their shape rebuilt on open.

Changing `ProfileFamily` updates the `ProfileSize` choices; the size is
kept when the new family has it.

### Wider profiles

`2040`, `2060`, `3060`, `3090`, `4080`, `40120` and `8080` are grids of the
square unit of the same series (20, 30 or 40 mm). There is a slot centred on
every outer unit edge and a bore through every unit. The first number is the
size along X and the second along Y, so a 2040 is 20 mm wide in X and 40 mm
in Y; rotate it with `Placement` to lay it the other way. They are made in
both families, matching the multi-unit profiles Rexroth makes. Like the
square profiles, they are solid where the real ones have hollow chambers.

### B-Type (Bosch Rexroth compatible)

The same slot model with real dimensions for Rexroth's slot 6, 8 and 10
series. They were measured from Motedis' B-Type CAD models and checked
against the Rexroth *Aluminum Framing* catalogue (R999001283):

| Parameter (mm)        | 2020 (slot 6) | 3030 (slot 8) | 4040 (slot 10) |
|-----------------------|-----:|-----:|-----:|
| Outer size            | 20   | 30   | 40   |
| Slot opening          | 6.2  | 8    | 10   |
| Lip thickness         | 1.5  | 2.2  | 6    |
| Cavity width          | 12   | 16.5 | 20.1 |
| Cavity straight walls | 1.44 | 2.75 | 2.536 |
| Slot floor width      | 6.88 | 8.4  | 12.172 |
| Slot depth            | 5.5  | 9    | 12.5 |
| Centre bore diameter  | 5.5  | 7.3  | 10   |
| Section area (mm²)    | 173.3 | 404.6 | 821.7 |
| Real profile area (mm²) | 162 | 314 | 561 |

The modelled area is larger than the real one because the model's core is
solid: the hollow chambers of the real profiles, the fillets, and the
shallow recess at each slot mouth are not modelled. The 4040 is Rexroth's
light `40x40L`. There is no 45x45 yet, for lack of a dimension source.

## Limitations

- `Generic` profiles have illustrative dimensions (see the warning above).
  Both families have sharp corners, no fillets, a solid core with no
  hollow chambers, a plain round bore rather than a tapping bore, and no
  slot detail such as the small grooves for spring-loaded T-nuts.
- Square units and grids of them only: no profiles with fewer slots
  (1N, 2N, 3N), no 45° or round profiles, and no 45 mm series.
- Straight extrusions only; no end cuts, mitres, tapped holes or machining.
- No hardware (brackets, T-nuts), frame generator, cut list or BOM.
- No custom task panel. Editing happens in the property editor.
- Tested only on FreeCAD 1.1.4 on Linux.

## Roadmap

Planned, not implemented:

- More manufacturer-compatible families (I-Type, item-compatible, …), and
  B-Type 45x45.
- Hollow cross-sections, for realistic area and mass.
- Cross-sections from user-supplied closed sketches or DXF outlines.
- Slot metadata (slot width, slot depth, core bore) for hardware placement.
- Extrusions following selected sketch edges.
- Automatic corner brackets and connectors.
- Frame generation.
- Cut lists and BOM export.

## License

LGPL-2.1-or-later; see [LICENSE](LICENSE). This covers code and icons.
