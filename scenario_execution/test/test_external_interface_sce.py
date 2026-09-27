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
"""get_scenario_parameters reads a scenario model file (.sce) as it reads the .osc it came from."""

import os
import tempfile
import unittest

import yaml

from scenario_execution import get_scenario_inputs, get_scenario_parameters
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.types import serialize

from .common import DebugLogger

_SCENARIO = """\
import osc.types

struct position:
    x: length
    y: length

scenario test_sce:
    count: int = 1
    velocity: speed = 1.0mps
    names: list of string = ['a']
    start: position = position(x: 1m, y: 2m)
    do serial:
        wait elapsed(1s)
"""


class TestExternalInterfaceSce(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.logger = DebugLogger("")
        self.osc = os.path.join(self._dir.name, "scenario.osc")
        with open(self.osc, "w", encoding="utf-8") as handle:
            handle.write(_SCENARIO)

    def tearDown(self):
        self._dir.cleanup()

    def _write_sce(self, content):
        path = os.path.join(self._dir.name, "scenario0.sce")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return path

    def _serialized(self):
        """The model as scenario_variation stores it."""
        parser = OpenScenario2Parser(self.logger)
        model = parser.load_internal_model(parser.parse_file(self.osc), self.osc)
        return yaml.safe_dump(serialize(model)['CompilationUnit']['_children'], sort_keys=False)

    def test_sce_parameters_match_osc(self):
        sce = self._write_sce(self._serialized())
        parameters = get_scenario_parameters(sce, self.logger)
        self.assertEqual(parameters, get_scenario_parameters(self.osc, self.logger))
        self.assertEqual(parameters, {"test_sce": [
            {"name": "count", "type": "int", "is_list": False},
            {"name": "velocity", "type": "speed", "is_list": False},
            {"name": "names", "type": "listofstring", "is_list": True},
            {"name": "start", "type": "position", "is_list": False},
        ]})

    def test_sce_inputs_are_the_model_file(self):
        sce = self._write_sce(self._serialized())
        self.assertEqual(get_scenario_inputs(sce, self.logger), [os.path.abspath(sce)])

    def test_unreadable_sce_names_the_file(self):
        sce = self._write_sce("not: [a, model")
        with self.assertRaisesRegex(ValueError, "scenario0.sce"):
            get_scenario_parameters(sce, self.logger)

    def test_unknown_extension_is_refused(self):
        path = os.path.join(self._dir.name, "scenario.txt")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(_SCENARIO)
        with self.assertRaisesRegex(ValueError, r"unknown extension '\.txt'"):
            get_scenario_parameters(path, self.logger)


if __name__ == '__main__':
    unittest.main()
