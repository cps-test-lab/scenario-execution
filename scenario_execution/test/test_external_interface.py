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

import os
import tempfile
import unittest
from importlib.resources import files

from scenario_execution import get_scenario_inputs, get_scenario_parameters, get_scenario_parameters_and_inputs

from .common import DebugLogger


class TestGetScenarioInputs(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.logger = DebugLogger("")

    def tearDown(self) -> None:
        self.dir.cleanup()

    def _write(self, name: str, text: str) -> str:
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _write_chain(self):
        lib_b = self._write("lib_b.osc", "enum b_enum: [b_one, b_two]\n")
        lib_a = self._write("lib_a.osc", f'import "{lib_b}"\n\nenum a_enum: [a_one, a_two]\n')
        entry = self._write("entry.osc", f"""\
import "{lib_a}"
import "{lib_b}"
import osc.types
import osc.some_external_library

scenario test_inputs:
    count: int = 1
    do serial:
        wait elapsed(1s)
""")
        return entry, lib_a, lib_b

    def test_lists_every_file_once_in_parse_order(self):
        entry, lib_a, lib_b = self._write_chain()
        types_osc = os.path.abspath(str(files("scenario_execution").joinpath("lib_osc", "types.osc")))
        self.assertEqual(get_scenario_inputs(entry, self.logger), [entry, lib_a, lib_b, types_osc])

    def test_skipped_external_library_is_not_listed(self):
        entry, _, _ = self._write_chain()
        inputs = get_scenario_inputs(entry, self.logger)
        self.assertFalse([path for path in inputs if "some_external_library" in path])

    def test_paths_are_absolute(self):
        entry, _, _ = self._write_chain()
        relative = os.path.relpath(entry)
        self.assertEqual(get_scenario_inputs(relative, self.logger)[0], entry)

    def test_missing_import_raises(self):
        entry = self._write("entry.osc", f"""\
import "{os.path.join(self.dir.name, 'missing.osc')}"

scenario test_inputs:
    do serial:
        wait elapsed(1s)
""")
        with self.assertRaisesRegex(ValueError, "missing.osc"):
            get_scenario_inputs(entry, self.logger)

    def test_missing_scenario_file_raises(self):
        with self.assertRaises(ValueError):
            get_scenario_inputs(os.path.join(self.dir.name, "missing.osc"), self.logger)

    def test_parameters_and_inputs_match_separate_calls(self):
        entry, _, _ = self._write_chain()
        parameters, inputs = get_scenario_parameters_and_inputs(entry, self.logger)
        self.assertEqual(parameters, get_scenario_parameters(entry, self.logger))
        self.assertEqual(inputs, get_scenario_inputs(entry, self.logger))
        self.assertEqual(parameters, {"test_inputs": [{"name": "count", "type": "int", "is_list": False}]})
