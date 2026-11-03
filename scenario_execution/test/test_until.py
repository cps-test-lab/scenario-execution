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
import unittest

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution import ScenarioExecution
from scenario_execution.model.model_blackboard import create_py_tree_blackboard
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.utils.logging import Logger


class TestUntil(unittest.TestCase):
    """The until directive: a behavior invocation ends when its event occurs."""
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

    def build(self, scenario_content):
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        create_py_tree_blackboard(model, self.tree, self.parser.logger, False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        return self.tree

    def execute(self, scenario_content):
        self.build(scenario_content)
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
    # what until ends
    #########

    def test_event_from_another_branch_ends_the_action(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    event enough_collected
    do parallel:
        run_process('""" + self.sleep_then_touch(marker, 10) + """') with:
            until @enough_collected
        serial:
            wait elapsed(1s)
            emit enough_collected
""")
        # The condition ends the invocation rather than judging it, so the branch succeeds -- and
        # the action is stopped on the way out.
        self.assertTrue(self.scenario_execution.process_results())
        self.assertFalse(os.path.exists(marker), "process outlived its until")

    def test_action_finishing_first_is_not_stopped(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    event never
    do parallel:
        run_process('""" + self.sleep_then_touch(marker, 1) + """') with:
            until @never
        serial:
            wait elapsed(5s)
            emit never
""")
        self.assertTrue(self.scenario_execution.process_results())
        self.assertTrue(os.path.exists(marker), "process was stopped although its until never fired")

    def test_until_bounds_a_whole_composition(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    do serial:
        log('collecting')
        run_process('""" + self.sleep_then_touch(marker, 10) + """')
        log('never reached')
    with:
        until elapsed(1s)
""")
        # Invalidation cascades through the composite, which is why until works on a block at all.
        self.assertTrue(self.scenario_execution.process_results())
        self.assertFalse(os.path.exists(marker), "process outlived the block's until")

    def test_several_untils_end_on_the_first_of_them(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    event early
    event late
    do parallel:
        run_process('""" + self.sleep_then_touch(marker, 10) + """') with:
            until @early
            until @late
        serial:
            wait elapsed(1s)
            emit early
""")
        self.assertTrue(self.scenario_execution.process_results())
        self.assertFalse(os.path.exists(marker), "neither until ended the action")

    #########
    # the if guard
    #########

    def test_guard_holds_the_until_until_the_condition_agrees(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    event batch_done
    var batches: int = 0
    do parallel:
        run_process('""" + self.sleep_then_touch(marker, 10) + """') with:
            until @batch_done if batches == 2
        serial:
            repeat(3)
            wait elapsed(1s)
            increment(batches)
            emit batch_done
""")
        # An event is a flag that stays set, so the first emit would end the action a second in.
        # The guard is re-checked every tick, which is what holds it to the second batch.
        self.assertTrue(self.scenario_execution.process_results())
        self.assertFalse(os.path.exists(marker), "process outlived its guarded until")

    def test_guard_that_never_holds_never_ends_the_action(self):
        marker = self.marker_path()
        self.execute("""
import osc.helpers

scenario test:
    timeout(20s)
    event batch_done
    var batches: int = 0
    do parallel:
        run_process('""" + self.sleep_then_touch(marker, 1) + """') with:
            until @batch_done if batches == 99
        serial:
            wait elapsed(0.5s)
            emit batch_done
""")
        self.assertTrue(self.scenario_execution.process_results())
        self.assertTrue(os.path.exists(marker), "the guard did not hold the until back")

    #########
    # where until ends up in the tree
    #########

    def test_until_wraps_outside_a_modifier_whatever_the_order(self):
        def shape(scenario_content):
            self.setUp()
            tree = self.build(scenario_content)
            invocation = tree.children[0].children[0]
            return (type(invocation).__name__,
                    [type(child).__name__ for child in invocation.children])

        before = shape("""
import osc.helpers

scenario test:
    event ev
    do serial:
        log('a') with:
            until @ev
            failure_is_success()
""")
        after = shape("""
import osc.helpers

scenario test:
    event ev
    do serial:
        log('a') with:
            failure_is_success()
            until @ev
""")
        # until is not a modifier: it bounds the whole invocation, so where in the block it was
        # written cannot change what it bounds.
        self.assertEqual(before, after)
        self.assertEqual(('Parallel', ['FailureIsSuccess', 'TopicEquals']), before)
