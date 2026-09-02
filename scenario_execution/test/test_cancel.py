# Copyright (C) 2026 Frederik Pasch
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
import time
import unittest

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution import ScenarioExecution
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.utils.logging import Logger


class TestCancel(unittest.TestCase):
    """Mid-scenario cancellation: the cancel_after/succeed_after modifiers, and terminate()."""
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution = ScenarioExecution(debug=False,
                                                    log_model=False,
                                                    live_tree=False,
                                                    scenario_file='test',
                                                    output_dir='',
                                                    tick_period=0.05)
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

    def marker_path(self):
        """A path a spawned process writes to only if it is allowed to run to completion."""
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.close()
        os.unlink(handle.name)
        self.tmp_files.append(handle.name)
        return handle.name

    def sleep_then_touch(self, marker, seconds):
        """A script that leaves *marker* behind only if it is allowed to run for *seconds*.

        A script rather than an inline command because run_process splits its command on spaces,
        so a quoted 'sh -c' string would not survive the trip.
        """
        with tempfile.NamedTemporaryFile('w', delete=False, suffix='.sh') as script:
            script.write(f'#!/bin/sh\nsleep {seconds}\ntouch {marker}\n')
        self.tmp_files.append(script.name)
        os.chmod(script.name, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        return script.name

    #########
    # cancel_after
    #########

    def test_cancel_after_stops_the_action(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do serial:
        run_process('""" + self.sleep_then_touch(marker, 10) + """') with:
            cancel_after(1s)
""")
        # The process is killed, so run_process reports the non-zero exit and the branch fails.
        # cancel_after passes that verdict through -- that is the whole point of it.
        self.assertFalse(self.scenario_execution.process_results())
        self.assertFalse(os.path.exists(marker), "process outlived its cancel")

    def test_cancel_after_longer_than_the_action_does_not_fire(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do serial:
        run_process('""" + self.sleep_then_touch(marker, 1) + """') with:
            cancel_after(15s)
""")
        self.assertTrue(self.scenario_execution.process_results())
        self.assertTrue(os.path.exists(marker), "process was cancelled although it had time to finish")

    def test_cancel_after_on_a_non_cancellable_action_fails(self):
        # log() has no request_cancel(). A cancel that quietly did nothing would let this pass.
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do serial:
        log('hello') with:
            cancel_after(0s)
""")
        self.assertFalse(self.scenario_execution.process_results())

    #########
    # succeed_after
    #########

    def test_succeed_after_stops_the_action_and_succeeds(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do serial:
        run_process('""" + self.sleep_then_touch(marker, 10) + """') with:
            succeed_after(1s)
""")
        self.assertTrue(self.scenario_execution.process_results())
        self.assertFalse(os.path.exists(marker), "process outlived its cancel")

    def test_succeed_after_passes_through_an_early_failure(self):
        # Ends well inside the window with a non-zero exit: it did not do what was asked, so
        # succeed_after must not paper over it.
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do serial:
        run_process('false') with:
            succeed_after(15s)
""")
        self.assertFalse(self.scenario_execution.process_results())

    #########
    # cancelling on a condition, the OpenSCENARIO way
    #########

    def test_event_from_another_branch_cancels_the_action(self):
        """Cancel when something happens elsewhere, using only osc events.

        The signal crosses branches as an osc event, which is carried on the blackboard, so no
        action holds a reference to any other. one_of turns the event into the end of the action's
        branch, and terminate() stops the action on the way out. This is what a cancel triggered by
        a condition rather than a clock looks like.
        """
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    event ready
    do parallel:
        serial:
            one_of:
                run_process('""" + self.sleep_then_touch(marker, 10) + """')
                wait @ready
            emit end
        serial:
            srv: run_process('printf READY')
            process_log_check('srv', ['READY'])
            emit ready
""")
        self.assertTrue(self.scenario_execution.process_results())
        time.sleep(1)
        self.assertFalse(os.path.exists(marker), "action outlived the event that should have ended it")

    #########
    # terminate()
    #########

    def test_one_of_stops_the_losing_branch(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do one_of:
        run_process('""" + self.sleep_then_touch(marker, 10) + """')
        wait elapsed(1s)
""")
        self.assertTrue(self.scenario_execution.process_results())
        time.sleep(1)
        self.assertFalse(os.path.exists(marker), "losing one_of branch kept running")

    def test_timeout_stops_the_action(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do serial:
        run_process('""" + self.sleep_then_touch(marker, 10) + """') with:
            timeout(1s)
""")
        self.assertFalse(self.scenario_execution.process_results())
        time.sleep(1)
        self.assertFalse(os.path.exists(marker), "timed-out action kept running")

    def test_terminate_does_not_cancel_on_success(self):
        # A short process finishes on its own; the SUCCESS stop must not be mistaken for
        # abandonment, or every completed action would be torn down as if it had been cancelled.
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do serial:
        run_process('""" + self.sleep_then_touch(marker, 1) + """')
        log('done')
""")
        self.assertTrue(self.scenario_execution.process_results())
        self.assertTrue(os.path.exists(marker))
