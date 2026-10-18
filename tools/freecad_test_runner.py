# SPDX-License-Identifier: LGPL-2.1-or-later
"""Run the tests/ suite inside FreeCAD and exit with unittest's status.

Usage: FreeCADCmd tools/freecad_test_runner.py   (see tools/run_tests.sh)
The addon must be installed in FreeCAD's user Mod directory.
"""

import os
import sys
import unittest

tests_dir = os.environ.get("TSLOT_TESTS_DIR") or os.path.join(os.getcwd(), "tests")
suite = unittest.defaultTestLoader.discover(tests_dir, top_level_dir=tests_dir)
result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
sys.stdout.flush()
# FreeCAD intercepts SystemExit, so leave the process directly.
os._exit(0 if result.wasSuccessful() else 1)
