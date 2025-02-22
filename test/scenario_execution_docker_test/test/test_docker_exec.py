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

import py_trees
import unittest
import tempfile
from scenario_execution import ScenarioExecution
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.utils.logging import Logger

from antlr4.InputStream import InputStream


class TestDockerExec(unittest.TestCase):
    # pylint: disable=missing-function-docstring,missing-class-docstring

    def setUp(self) -> None:
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution = ScenarioExecution(debug=False, log_model=False, live_tree=False,
                                                    scenario_file="test.osc", output_dir=None)
        self.tree = py_trees.composites.Sequence(name="", memory=True)
        self.tmp_file = tempfile.NamedTemporaryFile()

    def parse(self, scenario_content):
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution.tree = self.tree
        self.scenario_execution.run()

    def test_success(self):
        self.parse("""
import osc.docker
import osc.helpers

scenario test_success:
    timeout(30s)
    do parallel:
        docker_run(image: 'ubuntu', command: 'sleep 10', detach: true, container_name: 'sleeping_beauty_exec_success', remove: true)
        serial: 
            docker_exec(container: 'sleeping_beauty_exec_success', command: 'echo hello world')
            emit end
""")
        self.assertTrue(self.scenario_execution.process_results())

    def test_failure(self):
        self.parse("""
import osc.docker
import osc.helpers

scenario test_failure:
    timeout(15s)
    do parallel:
        docker_run(image: 'ubuntu', command: 'sleep 10', detach: true, container_name: 'sleeping_beauty_exec_fail', remove: true)
        serial: 
            docker_exec(container: 'sleeping_beauty_exec_fail', command: 'ls UKNOWN_DIR')
""")
        self.assertFalse(self.scenario_execution.process_results())

    def test_failure_container_not_running(self):
        self.parse("""
import osc.docker
import osc.helpers

scenario test_failure_container_not_running:
    timeout(3s)
    do serial: 
        docker_exec(container: 'sleeping_beauty', command: 'echo hello world')
""")
        self.assertFalse(self.scenario_execution.process_results())
