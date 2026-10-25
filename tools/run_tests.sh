#!/usr/bin/env bash
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Run the test suite:
#   1. pure-Python tests with python3 (FreeCAD tests are skipped there);
#   2. the same suite inside headless FreeCAD (FreeCADCmd);
#   3. with --gui, a GUI smoke test inside the full FreeCAD GUI, rendered
#      offscreen (QT_QPA_PLATFORM=offscreen), so no display is needed.
#
# FreeCAD runs use a throw-away user data and temp directory whose Mod/
# contains a symlink to this checkout, so FreeCAD discovers the addon exactly
# as it would a real install, without touching your own FreeCAD setup.
#
# The Fasteners workbench (needed for screws) is linked into that Mod/ too,
# from FASTENERS_DIR or your own FreeCAD Mod directory; without it, the
# screw tests are skipped.
#
# FREECAD_BIN_DIR or the flatpak selects FreeCAD. By default FreeCADCmd /
# FreeCAD on PATH are used, falling back to the Flathub flatpak.
#
#   tools/run_tests.sh            # pure Python + headless FreeCAD
#   tools/run_tests.sh --gui      # ... plus the GUI smoke test
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"

gui=0
[[ "${1:-}" == "--gui" ]] && gui=1

echo "== Pure-Python tests"
python3 -m unittest discover -s tests -v

sandbox="$(mktemp -d "${TMPDIR:-/tmp}/tslot-freecad-XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT
mkdir -p "$sandbox/data/Mod" "$sandbox/tmp"
ln -s "$repo" "$sandbox/data/Mod/TSlotWorkbench"

fasteners="${FASTENERS_DIR:-}"
if [[ -z "$fasteners" ]]; then
    for dir in "$HOME"/.local/share/FreeCAD/*/Mod/fasteners \
               "$HOME"/.var/app/org.freecad.FreeCAD/data/FreeCAD/*/Mod/fasteners \
               "$HOME"/Library/Application\ Support/FreeCAD/*/Mod/fasteners; do
        [[ -f "$dir/FastenersCmd.py" ]] && fasteners="$dir"
    done
fi
if [[ -n "$fasteners" ]]; then
    echo "== Using the Fasteners workbench from $fasteners"
    ln -s "$fasteners" "$sandbox/data/Mod/fasteners"
else
    echo "== Fasteners workbench not found: screw tests will be skipped" >&2
fi

env_vars=(
    "FREECAD_USER_DATA=$sandbox/data"
    "FREECAD_USER_TEMP=$sandbox/tmp"
    "TSLOT_TESTS_DIR=$repo/tests"
    "QT_QPA_PLATFORM=offscreen"
)

# run_freecad <FreeCADCmd|FreeCAD> <script>
run_freecad() {
    local binary="$1" script="$2"
    if [[ -n "${FREECAD_BIN_DIR:-}" ]]; then
        env "${env_vars[@]}" "$FREECAD_BIN_DIR/$binary" "$script"
    elif command -v "$binary" >/dev/null; then
        env "${env_vars[@]}" "$binary" "$script"
    elif flatpak info org.freecad.FreeCAD >/dev/null 2>&1; then
        local args=(--filesystem="$sandbox" --filesystem="$repo")
        [[ -n "$fasteners" ]] && args+=(--filesystem="$fasteners")
        for v in "${env_vars[@]}"; do args+=(--env="$v"); done
        flatpak run "${args[@]}" --command="$binary" org.freecad.FreeCAD "$script"
    else
        echo "== FreeCAD ($binary) not found: FreeCAD tests NOT run" >&2
        return 2
    fi
}

echo "== FreeCAD integration tests (headless)"
run_freecad FreeCADCmd "$repo/tools/freecad_test_runner.py"

if (( gui )); then
    echo "== FreeCAD GUI smoke test (offscreen)"
    run_freecad FreeCAD "$repo/tools/gui_smoke_test.py"
fi
