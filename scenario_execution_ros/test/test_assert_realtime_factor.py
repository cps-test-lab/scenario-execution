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

import unittest
import threading
import time
import py_trees

import rclpy
from rosgraph_msgs.msg import Clock

from scenario_execution_ros import ROSScenarioExecution
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.utils.logging import Logger
from antlr4.InputStream import InputStream

CLOCK_PERIOD = 0.05  # wall seconds between /clock messages


class TestAssertRealtimeFactor(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        rclpy.init()
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution_ros = ROSScenarioExecution()
        self.node = rclpy.create_node('test_node')
        self.publisher = self.node.create_publisher(Clock, "/clock", 10)
        # The simulation time the test pretends to have reached. Each tick advances it by the elapsed
        # wall time times self.rtf, so the published realtime factor is exactly self.rtf even though
        # the ROS timer fires late under a loaded executor.
        self.sim_time = 0.
        self.last_publish_wall = None
        self.rtf = 1.
        self.stall_next = 0  # number of upcoming ticks that publish no sim-time progress
        self.publish_clock = True
        self.start_wall = time.monotonic()
        self.publish_timer = self.node.create_timer(CLOCK_PERIOD, self.publish_messages)
        self.executor = rclpy.executors.MultiThreadedExecutor()
        self.executor.add_node(self.node)
        self.executor_thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.executor_thread.start()
        self.tree = py_trees.composites.Sequence(name="", memory=True)

    def execute(self, scenario_content):
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution_ros.scenarios_list = [(self.tree, {}, None)]
        self.scenario_execution_ros.run()

    def publish_messages(self):
        if not self.publish_clock:
            return
        now = time.monotonic()
        delta_wall = 0. if self.last_publish_wall is None else now - self.last_publish_wall
        self.last_publish_wall = now
        if self.stall_next > 0:
            self.stall_next -= 1  # publish the same sim time again: one sample at realtime factor 0
        else:
            self.sim_time += self.rtf * delta_wall
        msg = Clock()
        msg.clock.sec = int(self.sim_time)
        msg.clock.nanosec = int((self.sim_time - int(self.sim_time)) * 1e9)
        self.publisher.publish(msg)

    def elapsed(self):
        return time.monotonic() - self.start_wall

    def tearDown(self):
        self.node.destroy_node()
        rclpy.try_shutdown()


# TESTS PERFORMED
# 1. Case 1: a clock running at realtime passes a 'realtime_factor >= 0.5' assertion.
# 2. Case 2: a clock running at a fifth of realtime fails it.
# 3. Case 3 & 4: the grace period suppresses a degraded bring-up phase; without it the same run fails.
# 4. Case 5 & 6: a single stalled sample is smoothed away by rolling_average_count, but trips the
#    check when the rolling average is over a single sample.
# 5. Case 7: no /clock at all keeps the action running rather than failing it.
# 6. Case 8: the action re-arms correctly on retrigger.

    def test_case_1(self):
        # healthy clock, assertion holds -> the scenario ends on its own timeout arm
        self.rtf = 1.0
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_assert_realtime_factor:
    do parallel:
        serial:
            assert_realtime_factor(
                realtime_factor: 0.5,
                rolling_average_count: 5,
                grace_period: 0s)
            emit fail
        serial:
            wait elapsed(5s)
            emit end
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution_ros.process_results())

    def test_case_2(self):
        # degraded clock, assertion violated -> the action fails the scenario
        self.rtf = 0.2
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_assert_realtime_factor:
    do parallel:
        assert_realtime_factor(
            realtime_factor: 0.5,
            rolling_average_count: 5,
            grace_period: 0s)
        serial:
            wait elapsed(10s)
            emit end
"""
        self.execute(scenario_content)
        self.assertFalse(self.scenario_execution_ros.process_results())

    def test_case_3(self):
        # degraded during bring-up only, covered by the grace period -> passes
        self.rtf = 0.1

        def recover():
            if self.elapsed() > 3.0:
                self.rtf = 1.0
        self.node.create_timer(0.1, recover)

        scenario_content = """
import osc.ros
import osc.helpers

scenario test_assert_realtime_factor:
    do parallel:
        serial:
            assert_realtime_factor(
                realtime_factor: 0.5,
                rolling_average_count: 5,
                grace_period: 5s)
            emit fail
        serial:
            wait elapsed(10s)
            emit end
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution_ros.process_results())

    def test_case_4(self):
        # the very same run without a grace period fails, which is what shows case 3 was the grace
        # period doing the work rather than lucky timing
        self.rtf = 0.1

        def recover():
            if self.elapsed() > 3.0:
                self.rtf = 1.0
        self.node.create_timer(0.1, recover)

        scenario_content = """
import osc.ros
import osc.helpers

scenario test_assert_realtime_factor:
    do parallel:
        assert_realtime_factor(
            realtime_factor: 0.5,
            rolling_average_count: 5,
            grace_period: 0s)
        serial:
            wait elapsed(10s)
            emit end
"""
        self.execute(scenario_content)
        self.assertFalse(self.scenario_execution_ros.process_results())

    def test_case_5(self):
        # a single stalled sample among healthy ones is smoothed away by the rolling average
        self.rtf = 1.0

        def stall_once():
            self.stall_next = 1
            stall_timer.cancel()
        stall_timer = self.node.create_timer(2.0, stall_once)

        scenario_content = """
import osc.ros
import osc.helpers

scenario test_assert_realtime_factor:
    do parallel:
        serial:
            assert_realtime_factor(
                realtime_factor: 0.5,
                rolling_average_count: 20,
                grace_period: 0s)
            emit fail
        serial:
            wait elapsed(6s)
            emit end
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution_ros.process_results())

    def test_case_6(self):
        # the same single stalled sample trips the check when the window is a single sample
        self.rtf = 1.0

        def stall_once():
            self.stall_next = 1
            stall_timer.cancel()
        stall_timer = self.node.create_timer(2.0, stall_once)

        scenario_content = """
import osc.ros
import osc.helpers

scenario test_assert_realtime_factor:
    do parallel:
        assert_realtime_factor(
            realtime_factor: 0.5,
            rolling_average_count: 1,
            grace_period: 0s)
        serial:
            wait elapsed(6s)
            emit end
"""
        self.execute(scenario_content)
        self.assertFalse(self.scenario_execution_ros.process_results())

    def test_case_7(self):
        # no /clock at all: the action keeps running instead of failing
        self.publish_clock = False
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_assert_realtime_factor:
    do parallel:
        serial:
            assert_realtime_factor(
                realtime_factor: 0.5,
                rolling_average_count: 5,
                grace_period: 0s)
            emit fail
        serial:
            wait elapsed(5s)
            emit end
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution_ros.process_results())

    def test_case_8(self):
        # retrigger: execute() must reset the window and the grace timer on every re-entry
        self.rtf = 0.2
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_assert_realtime_factor:
    do parallel:
        serial:
            repeat()
            assert_realtime_factor(
                realtime_factor: 0.5,
                rolling_average_count: 5,
                grace_period: 0s) with:
                    failure_is_success()
        time_out: serial:
            wait elapsed(8s)
            emit end
"""
        self.execute(scenario_content)
        self.assertTrue(self.scenario_execution_ros.process_results())
