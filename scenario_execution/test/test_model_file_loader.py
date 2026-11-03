# Copyright (C) 2026 Florian Mirus
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

import tempfile
import unittest

from antlr4.InputStream import InputStream
import py_trees
import yaml

from scenario_execution.model.model_file_loader import ModelFileLoader
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.types import serialize
from scenario_execution.utils.logging import Logger


class TestModelFileLoader(unittest.TestCase):

    def test_wait_on_variable_in_serialized_model(self):
        cases = (
            ("ready", "bool", "true", "ready == true"),
            ("session_id", "string", "'local-session'", 'session_id != ""'),
        )
        for variable, variable_type, initial_value, condition in cases:
            with self.subTest(variable=variable):
                self.check_serialized_wait(variable, variable_type, initial_value, condition)

    def check_serialized_wait(self, variable, variable_type, initial_value, condition):
        with tempfile.NamedTemporaryFile(suffix='.sce', mode='w') as model_file:
            scenario = f"""\
scenario test_{variable}:
    var {variable}: {variable_type} = {initial_value}
    do serial:
        wait {condition}
"""
            logger = Logger('test', False)
            parser = OpenScenario2Parser(logger)
            parsed = parser.parse_input_stream(InputStream(scenario))
            model = parser.load_internal_model(parsed, 'test.osc')
            yaml.safe_dump(serialize(model)['CompilationUnit']['_children'], model_file)
            model_file.flush()

            tree = ModelFileLoader(logger).process_file(model_file.name)[0][0]
            tree.tick_once()
            self.assertEqual(tree.status, py_trees.common.Status.SUCCESS)
            self.assertIn("wait", py_trees.display.unicode_tree(tree))
