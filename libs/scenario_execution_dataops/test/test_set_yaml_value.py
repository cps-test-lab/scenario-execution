# Copyright (C) 2025 Frederik Pasch
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

import py_trees
import unittest
import tempfile
from scenario_execution import ScenarioExecution
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.utils.logging import Logger

from antlr4.InputStream import InputStream
import yaml


class TestSetYamlValue(unittest.TestCase):
    # pylint: disable=missing-function-docstring,missing-class-docstring

    def setUp(self) -> None:
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution = ScenarioExecution(debug=False, log_model=False, live_tree=False,
                                                    scenario_file="test.osc", output_dir=None)
        self.tree = py_trees.composites.Sequence(name="", memory=True)
        self.tmp_file = tempfile.NamedTemporaryFile()

    def run_yaml_test(self, yaml_content, output_file=None, key_path=None, value=None, value_type=None, create_missing=True):
        scenario_content = """
import osc.helpers
import osc.dataops

scenario test:
    timeout(1s)
    do serial:
        set_yaml_value({FILE_PATH}{OUTPUT_FILE}{KEY_PATH}{VALUE}{VALUE_TYPE}{CREATE_MISSING})
""".format(FILE_PATH="" if self.tmp_file is None else f"'{self.tmp_file.name}'",
            OUTPUT_FILE="" if output_file == '' else f", output_file:'{output_file}'",
            KEY_PATH= f", key_path:'{key_path}'",
            VALUE= f", value:'{value}'",
            VALUE_TYPE="" if value_type is None else f", value_type:'{value_type}'",
            CREATE_MISSING= f", create_missing:{str(create_missing).lower()}"
            )
        print(scenario_content)

        with open(self.tmp_file.name, 'w') as f:
            f.write(yaml_content)
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution.tree = self.tree
        self.scenario_execution.run()

    def test_success(self):
        self.run_yaml_test(yaml_content="""
config:
  servers:
    host: localhost
""", output_file='', key_path='config.servers.host', value='127.0.0.1', create_missing=False)
        self.assertTrue(self.scenario_execution.process_results())
        with open(self.tmp_file.name, 'r') as f:
            file_dict = yaml.safe_load(f)

        expected_dict = {
            "config": {
                "servers": {
                    "host": "127.0.0.1"
                }
            }
        }

        self.assertEqual(file_dict, expected_dict)

    def test_success_create_missing(self):
        self.run_yaml_test(yaml_content="""
config:
  servers:
    host: localhost
""", output_file='', key_path='config.servers.unknown', value='NEW_VALUE', create_missing=True)
        self.assertTrue(self.scenario_execution.process_results())
        with open(self.tmp_file.name, 'r') as f:
            file_dict = yaml.safe_load(f)

        expected_dict = {
            "config": {
                "servers": {
                    "host": "localhost",
                    "unknown": "NEW_VALUE"
                }
            }
        }

        self.assertEqual(file_dict, expected_dict)

    def test_failure_create_missing(self):
        self.run_yaml_test(yaml_content="""
config:
  servers:
    host: localhost
""", output_file='', key_path='config.servers.unknown', value='NEW_VALUE', create_missing=False)
        self.assertFalse(self.scenario_execution.process_results())
        with open(self.tmp_file.name, 'r') as f:
            file_dict = yaml.safe_load(f)

        # File should remain unchanged since create_missing=False
        expected_dict = {
            "config": {
                "servers": {
                    "host": "localhost"
                }
            }
        }

        self.assertEqual(file_dict, expected_dict)

    def test_success_int_as_string(self):
        self.run_yaml_test(yaml_content="""
config:
  value: 1
""", output_file='', key_path='config.value', value='42', create_missing=False)
        self.assertTrue(self.scenario_execution.process_results())
        with open(self.tmp_file.name, 'r') as f:
            file_dict = yaml.safe_load(f)

        # File should remain unchanged since create_missing=False
        expected_dict = {
            "config": {
                "value": '42'
            }
        }

        self.assertEqual(file_dict, expected_dict)


    def test_success_int_as_int(self):
        self.run_yaml_test(yaml_content="""
config:
  value: 1
""", output_file='', key_path='config.value', value='42', value_type='int', create_missing=False)
        self.assertTrue(self.scenario_execution.process_results())
        with open(self.tmp_file.name, 'r') as f:
            file_dict = yaml.safe_load(f)

        # File should remain unchanged since create_missing=False
        expected_dict = {
            "config": {
                "value": 42
            }
        }

        self.assertEqual(file_dict, expected_dict)



    def test_success_dict(self):
        self.run_yaml_test(yaml_content="""
config:
  value: 1
""", output_file='', key_path='config.value', value='{\\"key\\": \\"value\\", \\"subdict\\": {\\"subkey\\": \\"subvalue\\"}}', value_type='dict', create_missing=False)
        self.assertTrue(self.scenario_execution.process_results())
        with open(self.tmp_file.name, 'r') as f:
            file_dict = yaml.safe_load(f)

        # File should remain unchanged since create_missing=False
        expected_dict = {
            "config": {
                "value": {
                    "key": "value",
                    "subdict": {
                        "subkey": "subvalue"
                    }
                }
            }
        }

        self.assertEqual(file_dict, expected_dict)
