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

import threading
import time
import unittest

import py_trees
import rclpy
from antlr4.InputStream import InputStream
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from example_interfaces.action import Fibonacci

from scenario_execution_ros import ROSScenarioExecution
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.utils.logging import Logger


class TestRosActionCancel(unittest.TestCase):
    """Mid-trial cancellation of a ROS action goal, and the status assertion that makes it a test."""
    # pylint: disable=missing-function-docstring

    def setUp(self):
        rclpy.init()
        self.node = rclpy.create_node('test_node_action_cancel')

        self.executor = rclpy.executors.MultiThreadedExecutor()
        self.executor.add_node(self.node)
        self.executor_thread = threading.Thread(target=self.executor.spin)
        self.executor_thread.start()

        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution_ros = ROSScenarioExecution()

        #: Set by the server when a cancel actually reaches it. The scenario's own verdict cannot
        #: distinguish "cancelled the goal" from "gave up locally", so the server is the witness.
        self.cancel_seen = threading.Event()
        #: Goals accepted so far, for the preemption probe.
        self.goals_accepted = 0
        #: Delay before the goal is accepted, to open the window in which a cancel can arrive
        #: before there is a goal handle to cancel.
        self.goal_accept_delay = 0.0
        self.abort_goal = False

        self.action_server = ActionServer(
            self.node,
            Fibonacci,
            '/test_action',
            execute_callback=self.execute_callback,
            callback_group=ReentrantCallbackGroup(),
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback)
        self.tree = py_trees.composites.Sequence(name="", memory=True)

    def tearDown(self):
        self.action_server.destroy()
        self.node.destroy_node()
        rclpy.try_shutdown()
        self.executor_thread.join()

    def execute(self, scenario_content):
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution_ros.scenarios_list = [(self.tree, {}, None)]
        self.scenario_execution_ros.run()

    def goal_callback(self, goal_request):
        if self.goal_accept_delay:
            time.sleep(self.goal_accept_delay)
        self.goals_accepted += 1
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        self.cancel_seen.set()
        return CancelResponse.ACCEPT

    def execute_callback(self, goal_handle):
        """A goal that takes ~5s and honours a cancel promptly."""
        for _ in range(50):
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return Fibonacci.Result()
            time.sleep(0.1)
        if self.abort_goal:
            goal_handle.abort()
        else:
            goal_handle.succeed()
        return Fibonacci.Result()

    ACTION = ("action_name: '/test_action', action_type: 'example_interfaces.action.Fibonacci', "
              "data: '{\\\"order\\\": 3}'")

    #########
    # cancel_after
    #########

    def test_cancel_after_with_expected_canceled_succeeds(self):
        self.execute("""
import osc.helpers
import osc.ros

scenario test:
    timeout(30s)
    do serial:
        action_call(""" + self.ACTION + """, expected_status: action_goal_status!canceled) with:
            cancel_after(1s)
""")
        self.assertTrue(self.cancel_seen.wait(timeout=5), "no cancel reached the action server")
        self.assertTrue(self.scenario_execution_ros.process_results())

    def test_cancel_after_without_expected_status_fails(self):
        # Same cancellation, default expectation: the goal ended CANCELED where SUCCEEDED was
        # required, so the scenario must fail. This is what makes expected_status an assertion
        # rather than a way of tolerating whatever happened.
        self.execute("""
import osc.helpers
import osc.ros

scenario test:
    timeout(30s)
    do serial:
        action_call(""" + self.ACTION + """) with:
            cancel_after(1s)
""")
        self.assertTrue(self.cancel_seen.wait(timeout=5), "no cancel reached the action server")
        self.assertFalse(self.scenario_execution_ros.process_results())

    #########
    # expected_status on its own
    #########

    def test_expected_status_aborted(self):
        self.abort_goal = True
        self.execute("""
import osc.helpers
import osc.ros

scenario test:
    timeout(30s)
    do serial:
        action_call(""" + self.ACTION + """, expected_status: action_goal_status!aborted)
""")
        self.assertTrue(self.scenario_execution_ros.process_results())

    def test_expected_status_rejects_success_on_acceptance(self):
        # A contradiction: success_on_acceptance ends the action before any terminal status exists.
        self.execute("""
import osc.helpers
import osc.ros

scenario test:
    timeout(30s)
    do serial:
        action_call(""" + self.ACTION + """, success_on_acceptance: true, expected_status: action_goal_status!canceled)
""")
        self.assertFalse(self.scenario_execution_ros.process_results())

    #########
    # terminate(): an abandoned branch must stop its goal
    #########

    def test_one_of_cancels_the_losing_branch(self):
        self.execute("""
import osc.helpers
import osc.ros

scenario test:
    timeout(30s)
    do one_of:
        action_call(""" + self.ACTION + """)
        wait elapsed(1s)
""")
        self.assertTrue(self.cancel_seen.wait(timeout=5),
                        "losing one_of branch left its goal running on the server")

    def test_timeout_cancels_the_goal(self):
        self.execute("""
import osc.helpers
import osc.ros

scenario test:
    timeout(30s)
    do serial:
        action_call(""" + self.ACTION + """) with:
            timeout(1s)
""")
        self.assertTrue(self.cancel_seen.wait(timeout=5),
                        "timed-out action left its goal running on the server")

    #########
    # Preemption probe: is a staggered second goal expressible without any new feature?
    #########

    def test_staggered_second_goal_is_expressible(self):
        """The upstream preempt oracle: both goals accepted, the second one SUCCEEDED.

        No new feature is involved. success_on_acceptance makes the first call fire-and-forget, so
        the branch finishes at acceptance and leaves the goal running for the second to supersede;
        the second call waits for the terminal status and so carries the assertion. Whether the
        server preempts is the server's business -- what is being checked here is that the scenario
        shape exists.
        """
        self.execute("""
import osc.helpers
import osc.ros

scenario test:
    timeout(30s)
    do parallel:
        action_call(""" + self.ACTION + """, success_on_acceptance: true)
        serial:
            wait elapsed(1s)
            action_call(""" + self.ACTION + """)
""")
        self.assertTrue(self.scenario_execution_ros.process_results())
        self.assertEqual(self.goals_accepted, 2, "both goals should have been accepted")
