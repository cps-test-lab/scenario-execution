# Copyright (C) 2026 Florian Mirus
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

import os
import stat
import tempfile
import unittest

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution import ScenarioExecution
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.utils.logging import Logger


class TestProcessLogCheck(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution = ScenarioExecution(debug=False,
                                                    log_model=False,
                                                    live_tree=False,
                                                    scenario_file='test',
                                                    output_dir='',
                                                    tick_period=0.01)
        self.tree = py_trees.composites.Sequence(name="", memory=True)
        self.tmp_files = []

    def tearDown(self):
        for filename in self.tmp_files:
            try:
                os.unlink(filename)
            except FileNotFoundError:
                pass

    def execute(self, scenario_content):
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution.scenarios_list = [(self.tree, {}, None)]
        self.scenario_execution.run()

    def create_script(self, content):
        with tempfile.NamedTemporaryFile('w', delete=False) as script:
            script.write('#!/bin/sh\n')
            script.write(content)
        self.tmp_files.append(script.name)
        os.chmod(script.name, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return script.name

    def test_success_after_process_finished(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_process_log_check:
    timeout(5s)
    do serial:
        proc: run_process('printf READY')
        process_log_check('proc', ['READY'])
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution.process_results())

    def test_success_while_process_is_running(self):
        script = self.create_script('echo READY\nsleep 10\n')
        scenario_content = f"""
import osc.types
import osc.helpers

scenario test_process_log_check:
    do parallel:
        proc: run_process('{script}', wait_for_shutdown: false, shutdown_timeout: 1s)
        serial:
            process_log_check('proc', ['READY'])
            emit end
        time_out: serial:
            wait elapsed(5s)
            emit fail
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution.process_results())

    def test_failure_when_process_finishes_without_match(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_process_log_check:
    timeout(5s)
    do serial:
        proc: run_process('printf OTHER')
        process_log_check('proc', ['READY'])
"""
        self.execute(scenario_content)
        self.assertFalse(self.scenario_execution.process_results())

    def test_failure_for_unknown_process(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_process_log_check:
    timeout(5s)
    do serial:
        process_log_check('unknown', ['READY'])
"""
        self.execute(scenario_content)
        self.assertFalse(self.scenario_execution.process_results())

    def test_failure_for_unlabeled_process(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_process_log_check:
    timeout(5s)
    do serial:
        run_process('printf READY')
        process_log_check('run_process', ['READY'])
"""
        self.execute(scenario_content)
        self.assertFalse(self.scenario_execution.process_results())


if __name__ == '__main__':
    unittest.main()
