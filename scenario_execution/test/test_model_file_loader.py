# Copyright (C) 2026 Frederik Pasch
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

"""Tests for loading serialized scenario models."""

import os
import sys
import tempfile
import unittest
from unittest import mock

from antlr4.InputStream import InputStream
import py_trees
import yaml

from scenario_execution.model.error import OSC2ParsingError
from scenario_execution.model.model_file_loader import ModelFileLoader
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.types import serialize
from scenario_execution.scenario_execution_base import ScenarioExecution, main
from scenario_execution.utils.logging import Logger


class TestModelFileLoader(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def test_wait_on_variable_in_serialized_model(self):
        cases = (
            ("ready", "bool", "true", "ready == true"),
            ("session_id", "string", "'local-session'", 'session_id != ""'),
        )
        for variable, variable_type, initial_value, condition in cases:
            with self.subTest(variable=variable):
                self._check_serialized_wait(variable, variable_type, initial_value, condition)

    def _check_serialized_wait(self, variable, variable_type, initial_value, condition):
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
        with tempfile.NamedTemporaryFile(suffix='.sce', mode='w') as model_file:
            yaml.safe_dump(serialize(model)['CompilationUnit']['_children'], model_file)
            model_file.flush()

            tree = ModelFileLoader(logger).process_file(model_file.name)[0][0]
            tree.tick_once()
            self.assertEqual(tree.status, py_trees.common.Status.SUCCESS)
            self.assertIn(condition.replace(" ", ""), py_trees.display.unicode_tree(tree))

    def test_wait_in_serialized_model_without_source(self):
        scenario = """\
scenario test_no_source:
    var ready: bool = true
    do serial:
        wait ready == true
"""
        logger = Logger('test', False)
        parser = OpenScenario2Parser(logger)
        parsed = parser.parse_input_stream(InputStream(scenario))
        model = parser.load_internal_model(parsed, 'test.osc')

        def without_source(node):
            if isinstance(node, dict):
                return {key: without_source(value) for key, value in node.items() if key != '_ctx'}
            if isinstance(node, list):
                return [without_source(value) for value in node]
            return node
        with tempfile.NamedTemporaryFile(suffix='.sce', mode='w') as model_file:
            yaml.safe_dump(without_source(serialize(model)['CompilationUnit']['_children']), model_file)
            model_file.flush()

            tree = ModelFileLoader(logger).process_file(model_file.name)[0][0]
            tree.tick_once()
            self.assertEqual(tree.status, py_trees.common.Status.SUCCESS)
            self.assertIn("wait (source unavailable)", py_trees.display.unicode_tree(tree))

    def test_serialized_scenario_parameters_reach_runner(self):
        scenario = """\
scenario test_params:
    count: int = 7
    do serial:
        wait count == 7
"""
        logger = Logger('test', False)
        parser = OpenScenario2Parser(logger)
        parsed = parser.parse_input_stream(InputStream(scenario))
        model = parser.load_internal_model(parsed, 'test.osc')
        with tempfile.NamedTemporaryFile(suffix='.sce', mode='w') as model_file:
            yaml.safe_dump(serialize(model)['CompilationUnit']['_children'], model_file)
            model_file.flush()
            runner = ScenarioExecution(debug=False, log_model=False, live_tree=False,
                                       scenario_file=model_file.name, output_dir='')
            self.assertTrue(runner.parse())
            self.assertEqual(runner.scenario_params, {'count': 7})

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.corrupt = os.path.join(self.tmp_dir.name, 'corrupt.sce')
        with open(self.corrupt, 'w', encoding='utf-8') as f:
            f.write('- CompilationUnit: [unterminated\n')
        self.missing = os.path.join(self.tmp_dir.name, 'missing.sce')

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_load_file_corrupt(self):
        with self.assertRaises(ValueError) as ctx:
            ModelFileLoader(Logger('test', False)).load_file(self.corrupt, False)
        self.assertIn(self.corrupt, str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, yaml.YAMLError)

    def test_load_file_missing(self):
        with self.assertRaises(ValueError) as ctx:
            ModelFileLoader(Logger('test', False)).load_file(self.missing, False)
        self.assertIn(self.missing, str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, FileNotFoundError)

    def test_load_file_not_a_model(self):
        not_a_model = os.path.join(self.tmp_dir.name, 'empty.sce')
        with open(not_a_model, 'w', encoding='utf-8'):
            pass
        with self.assertRaises(ValueError) as ctx:
            ModelFileLoader(Logger('test', False)).load_file(not_a_model, False)
        self.assertIn(not_a_model, str(ctx.exception))

    def test_runner_model_without_scenario(self):
        logger = Logger('test', False)
        parser = OpenScenario2Parser(logger)
        parsed = parser.parse_input_stream(InputStream("struct position:\n    x: int\n"))
        model = parser.load_internal_model(parsed, 'test.osc')
        no_scenario = os.path.join(self.tmp_dir.name, 'no_scenario.sce')
        with open(no_scenario, 'w', encoding='utf-8') as model_file:
            yaml.safe_dump(serialize(model)['CompilationUnit']['_children'], model_file)
        result = self._parse(no_scenario)
        self.assertIn("No scenario defined", result.failure_output)
        self.assertIn(no_scenario, result.failure_output)

    def test_runner_refuses_parameter_file_for_model(self):
        logger = Logger('test', False)
        parser = OpenScenario2Parser(logger)
        parsed = parser.parse_input_stream(InputStream("scenario test_params:\n    count: int = 7\n"))
        model = parser.load_internal_model(parsed, 'test.osc')
        model_path = os.path.join(self.tmp_dir.name, 'params.sce')
        with open(model_path, 'w', encoding='utf-8') as model_file:
            yaml.safe_dump(serialize(model)['CompilationUnit']['_children'], model_file)
        parameter_file = os.path.join(self.tmp_dir.name, 'overrides.yaml')
        with open(parameter_file, 'w', encoding='utf-8') as overrides:
            yaml.safe_dump({'test_params': {'count': 8}}, overrides)
        for template in (False, True):
            with self.subTest(template=template):
                result = self._parse(model_path, scenario_parameter_file=parameter_file,
                                     create_scenario_parameter_file_template=template)
                self.assertIn(model_path, result.failure_output)
                self.assertIn(".osc scenario", result.failure_output)

    def test_runner_error_names_source_file(self):
        logger = Logger('test', False)
        parser = OpenScenario2Parser(logger)
        source = os.path.join(self.tmp_dir.name, 'source_dir', 'counting.osc')
        parsed = parser.parse_input_stream(InputStream("scenario test_count:\n    count: int = 7\n    do serial:\n        wait count\n"))
        model = parser.load_internal_model(parsed, source)
        model_path = os.path.join(self.tmp_dir.name, 'counting.sce')
        with open(model_path, 'w', encoding='utf-8') as model_file:
            yaml.safe_dump(serialize(model)['CompilationUnit']['_children'], model_file)
        with open(model_path, encoding='utf-8') as model_file:
            self.assertNotIn('source_dir', model_file.read())
        result = self._parse(model_path)
        self.assertIn("(line: 4, column: 13 in 'counting.osc') -> count:", result.failure_output)

    def _parse(self, scenario_file, **kwargs):
        scenario_execution = ScenarioExecution(debug=False,
                                               log_model=False,
                                               live_tree=False,
                                               scenario_file=scenario_file,
                                               output_dir="",
                                               **kwargs)
        self.assertFalse(scenario_execution.parse())
        self.assertEqual(len(scenario_execution.results), 1)
        result = scenario_execution.results[0]
        self.assertFalse(result.result)
        self.assertEqual(result.failure_message, "parsing failed")
        return result

    def test_runner_corrupt(self):
        result = self._parse(self.corrupt)
        self.assertIn(self.corrupt, result.failure_output)

    def test_runner_missing(self):
        result = self._parse(self.missing)
        self.assertIn(self.missing, result.name)

    def test_main_corrupt(self):
        output_dir = os.path.join(self.tmp_dir.name, 'out')
        with mock.patch.object(sys, 'argv', ['scenario_execution', self.corrupt, '-o', output_dir]):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)
        with open(os.path.join(output_dir, 'test.xml'), encoding='utf-8') as report:
            text = report.read()
        self.assertIn('<failure', text)
        self.assertIn(self.corrupt, text)


class TestErrorWithoutSource(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def test_error_from_deserialized_element(self):
        error = OSC2ParsingError(msg='Invalid event condition.', context=(4, 13, 'count', None))
        self.assertEqual(str(error), "(line: 4, column: 13) -> count: Invalid event condition.")

    def test_error_from_element_without_source(self):
        error = OSC2ParsingError(msg='Invalid event condition.', context=(None, None, None, None))
        self.assertEqual(str(error), "(line: None, column: None): Invalid event condition.")
