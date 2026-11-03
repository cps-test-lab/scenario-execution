# Copyright (C) 2024 Intel Corporation
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

import unittest
import py_trees
from scenario_execution.scenario_execution_base import ScenarioExecution
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_to_py_tree import create_py_tree
from .common import DebugLogger
from antlr4.InputStream import InputStream


class TestExternalMethodsRandom(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        self.logger = DebugLogger("")
        self.parser = OpenScenario2Parser(self.logger)
        self.tree = py_trees.composites.Sequence(name="", memory=True)
        self.scenario_execution = ScenarioExecution(debug=False,
                                                    log_model=False,
                                                    live_tree=False,
                                                    scenario_file='test',
                                                    output_dir='', logger=self.logger)
        self.tree = py_trees.composites.Sequence(name="", memory=True)

    def execute(self, scenario_content):
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution.scenarios_list = [(self.tree, {}, None)]
        self.scenario_execution.run()

    def test_get_random_int(self):
        # Asserted on the drawn value rather than on how long a wait took. get_int is inclusive at
        # both ends, so a scenario waiting get_int(0, 5) seconds can legitimately wait the full
        # five; a stopwatch bound at five decides the verdict by the draw instead of by the code.
        scenario_content = """
import osc.helpers

scenario test_success:
    do serial:
        log(random.get_int(0, 5))
        emit end
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution.process_results())

        drawn = [int(msg) for msg in self.logger.logs_info if msg.lstrip("-").isdigit()]
        self.assertEqual(len(drawn), 1, f"expected one drawn value, logged: {self.logger.logs_info}")
        self.assertGreaterEqual(drawn[0], 0)
        self.assertLessEqual(drawn[0], 5)

    def test_get_random_string(self):
        scenario_content = """
import osc.helpers

scenario test_success:
    do serial:
        log(random.get_random_string(["test", "test-scenario", "scenario-test"]))
        emit end
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution.process_results())

        # Counted rather than filtered: asserting only about messages already known to be valid
        # passes whatever the method returns, including nothing at all.
        valid_strings = ["test", "test-scenario", "scenario-test"]
        chosen = [msg for msg in self.logger.logs_info if msg in valid_strings]
        self.assertEqual(len(chosen), 1, f"expected one chosen string, logged: {self.logger.logs_info}")
