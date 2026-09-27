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

"""
A .sce model file that cannot be loaded fails naming the file, through the loader and the runner.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock
from xml.etree import ElementTree

import yaml

from scenario_execution.model.model_file_loader import ModelFileLoader
from scenario_execution.scenario_execution_base import ScenarioExecution, main
from scenario_execution.utils.logging import Logger


class TestModelFileLoader(unittest.TestCase):
    # pylint: disable=missing-function-docstring

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

    def _parse(self, scenario_file):
        scenario_execution = ScenarioExecution(debug=False,
                                               log_model=False,
                                               live_tree=False,
                                               scenario_file=scenario_file,
                                               output_dir="")
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
        failure = ElementTree.parse(os.path.join(output_dir, 'test.xml')).find('testcase/failure')
        self.assertIn(self.corrupt, failure.text)
