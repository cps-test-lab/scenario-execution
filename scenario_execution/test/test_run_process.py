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

import os
import signal
import unittest
import py_trees
from scenario_execution import ScenarioExecution
from scenario_execution.actions.run_process import RunProcess
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.utils.logging import BaseLogger, Logger
from antlr4.InputStream import InputStream
from datetime import datetime


class TestScenarioExecutionSuccess(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution = ScenarioExecution(debug=False,
                                                    log_model=False,
                                                    live_tree=False,
                                                    scenario_file='test',
                                                    output_dir='')
        self.tree = py_trees.composites.Sequence(name="", memory=True)

    def execute(self, scenario_content):
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution.scenarios_list = [(self.tree, {}, None)]
        self.scenario_execution.run()

    def test_failure(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_run_process:
    timeout(10s)
    do serial:
        run_process() with:
            keep(it.command == 'false')
"""
        self.execute(scenario_content)
        self.assertFalse(self.scenario_execution.process_results())

    def test_success(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_run_process:
    timeout(10s)
    do serial:
        run_process() with:
            keep(it.command == 'true')
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution.process_results())

    def test_multi_element_command(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_run_process:
    timeout(10s)
    do serial:
        run_process('sleep 2')
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution.process_results())

    def test_wait_for_shutdown_false(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_run_process:
    timeout(3s)
    do serial:
        run_process('sleep 15', wait_for_shutdown: false)
"""
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution.scenarios_list = [(self.tree, {}, None)]

        start = datetime.now()
        self.scenario_execution.run()
        end = datetime.now()
        duration = (end-start).total_seconds()
        self.assertLessEqual(duration, 3.)
        self.assertTrue(self.scenario_execution.process_results())

    def test_signal_parsing(self):
        scenario_content = """
import osc.types
import osc.helpers

scenario test_run_process:
    do run_process('sleep 15', wait_for_shutdown: false, shutdown_signal: signal!sigint)
"""
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)


class RecordingLogger(BaseLogger):
    """Keeps what was logged, so a test can assert that being ignored was said out loud."""

    def __init__(self):
        super().__init__('test', False)
        self.messages = {'info': [], 'debug': [], 'warning': [], 'error': []}

    def info(self, msg: str) -> None:
        self.messages['info'].append(msg)

    def debug(self, msg: str) -> None:
        self.messages['debug'].append(msg)

    def warning(self, msg: str) -> None:
        self.messages['warning'].append(msg)

    def error(self, msg: str) -> None:
        self.messages['error'].append(msg)


class TestRunProcessReinitialise(unittest.TestCase):
    """A re-initialise must never spawn a second process over a running one.

    py_trees re-initialises every child that is not RUNNING, so an action parked in SUCCESS
    (``wait_for_shutdown: false``) is re-``initialise()``d -- and ``initialise()`` calls
    ``execute()``. If ``update()`` then spawns again, ``self.process`` is rebound to the newborn and
    the handle on the real child is lost: ``shutdown()`` signals the wrong process group, reports
    success, and a simulator that writes its results only on a clean stop writes none. That is how a
    stopping scenario orphaned its simulator and lost every run artifact.

    ``execute()`` + ``update()`` are driven directly here: that pair is exactly what a re-initialise
    performs, and it needs no ROS, no tick timer and no scenario file to reproduce.
    """

    def setUp(self) -> None:
        self.logger = RecordingLogger()
        self.action = RunProcess()
        self.action._set_base_properities('test_run_process', None, self.logger)  # pylint: disable=protected-access
        self.spawned_pids = []
        self.addCleanup(self._kill_spawned)

    def _kill_spawned(self):
        # Reap everything the test started, including the extra process an unfixed action spawns --
        # a leaked `sleep` would outlive the suite.
        for pid in self.spawned_pids:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def _reinitialise(self, command='sleep 30'):
        """One initialise+update cycle, as py_trees performs it. Returns the action's status."""
        self.action.execute(command, wait_for_shutdown=False)
        status = self.action.update()
        if self.action.process is not None and self.action.process.pid not in self.spawned_pids:
            self.spawned_pids.append(self.action.process.pid)
        return status

    def test_reinitialise_keeps_the_running_process(self):
        self.assertEqual(self._reinitialise(), py_trees.common.Status.SUCCESS)
        first = self.action.process
        self.assertIsNone(first.poll(), "the process under test should still be running")

        self.assertEqual(self._reinitialise(), py_trees.common.Status.SUCCESS)

        self.assertIs(self.action.process, first,
                      "a re-initialise spawned a second process and dropped the handle on the first")
        self.assertEqual(len(self.spawned_pids), 1, "exactly one process should have been spawned")

    def test_shutdown_kills_the_process_that_was_started(self):
        self._reinitialise()
        started = self.action.process
        self._reinitialise()

        self.action.shutdown()

        started.wait(10)
        self.assertIsNotNone(started.poll(),
                             "shutdown() must signal the process that is actually running")

    def test_reinitialise_after_exit_starts_a_new_process(self):
        # The guard must not turn into "an action can only ever run once".
        self._reinitialise('true')
        first = self.action.process
        first.wait(10)
        self.assertIsNotNone(first.poll())

        self._reinitialise('true')

        self.assertIsNot(self.action.process, first,
                         "a finished process must not block a legitimate re-run")

    def test_reinitialise_with_a_different_command_is_reported(self):
        self._reinitialise('sleep 30')
        first = self.action.process

        self._reinitialise('sleep 31')

        self.assertIs(self.action.process, first, "the running process must be kept")
        self.assertTrue(any('sleep 31' in msg for msg in self.logger.messages['warning']),
                        "ignoring a different command must be said out loud, not silently")
