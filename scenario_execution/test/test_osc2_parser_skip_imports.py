# Copyright (C) 2026 Frederik Pasch
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0
"""Skipping external imports skips reading them, not checking a name that cannot exist."""

import os
import tempfile
import unittest

from scenario_execution import get_scenario_parameters
from scenario_execution.model.osc2_parser import OpenScenario2Parser

from .common import DebugLogger

_SCENARIO = """\
import osc.types
import {library}

scenario test_skip:
    count: int = 1
    do serial:
        wait elapsed(1s)
"""


class TestSkipImports(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.logger = DebugLogger("")

    def tearDown(self):
        self._dir.cleanup()

    def _write(self, library):
        path = os.path.join(self._dir.name, "scenario.osc")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_SCENARIO.format(library=library))
        return path

    def _load(self, path, skip_imports):
        parser = OpenScenario2Parser(self.logger)
        return parser.load_internal_model(parser.parse_file(path), path, skip_imports=skip_imports)

    def test_misspelled_core_library_is_refused(self):
        path = self._write("osc.standard.base")
        with self.assertRaisesRegex(ValueError, 'No import library "standard.base" found.'):
            get_scenario_parameters(path, self.logger)

    def test_refusal_matches_full_parse(self):
        path = self._write("osc.types.extra")
        for skip_imports in (True, False):
            with self.subTest(skip_imports=skip_imports):
                with self.assertRaisesRegex(ValueError, 'No import library "types.extra" found.'):
                    self._load(path, skip_imports)

    def test_external_library_not_installed_is_skipped(self):
        path = self._write("osc.some_external_library")
        self.assertEqual(get_scenario_parameters(path, self.logger),
                         {"test_skip": [{"name": "count", "type": "int", "is_list": False}]})

    def test_external_library_not_installed_is_refused_by_full_parse(self):
        path = self._write("osc.some_external_library")
        with self.assertRaisesRegex(ValueError, 'No import library "some_external_library" found.'):
            self._load(path, skip_imports=False)


if __name__ == '__main__':
    unittest.main()
