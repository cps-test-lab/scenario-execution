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

"""Tests for running a scenario against simulated time.

Every case drives a synthetic /clock at a chosen rate, so what a duration in the
scenario counts can be compared against both timelines at once: how much simulated
time the scenario consumed, and how much host time that took.

The test's own node is created with use_global_arguments=False. It publishes the
/clock the runner waits for, so a node of the test's that followed /clock itself
would be waiting for its own output.
"""

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

CLOCK_PERIOD = 0.02  # host seconds between /clock messages


class SimTimeFixture(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    USE_SIM_TIME = True

    def setUp(self) -> None:
        if self.USE_SIM_TIME:
            rclpy.init(args=['--ros-args', '-p', 'use_sim_time:=true'])
        else:
            rclpy.init()
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution_ros = ROSScenarioExecution()
        self.node = rclpy.create_node('test_clock_publisher', use_global_arguments=False)
        self.publisher = self.node.create_publisher(Clock, "/clock", 10)
        self.sim_time = 0.
        self.last_publish_wall = None
        self.rtf = 1.
        self.publish_clock = True
        self.jump_back_at = None  # sim seconds after which /clock steps backwards once
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
        self.sim_time += self.rtf * delta_wall
        if self.jump_back_at is not None and self.sim_time > self.jump_back_at:
            self.sim_time = max(self.sim_time - 5.0, 0.001)
            self.jump_back_at = None
        msg = Clock()
        msg.clock.sec = int(self.sim_time)
        msg.clock.nanosec = int((self.sim_time - int(self.sim_time)) * 1e9)
        self.publisher.publish(msg)

    def elapsed(self):
        return time.monotonic() - self.start_wall

    def tearDown(self):
        try:
            self.node.destroy_node()
        except Exception:  # pylint: disable=broad-except
            pass
        rclpy.try_shutdown()


class TestScenarioOnSimulatedTime(SimTimeFixture):
    # pylint: disable=missing-function-docstring

    def test_wait_elapsed_counts_simulated_seconds(self):
        # At a quarter of realtime a 2s wait is 2 simulated seconds, so about 8 host seconds.
        # Were it counting host seconds it would take 2, which is what the spans below separate.
        # Both spans also carry the run's own bring-up, hence the bands rather than equalities.
        self.rtf = 0.25
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_wait_elapsed:
    do serial:
        wait elapsed(2s)
        emit end
"""
        sim_before = self.sim_time
        wall_before = time.monotonic()
        self.execute(scenario_content)
        sim_span = self.sim_time - sim_before
        wall_span = time.monotonic() - wall_before

        self.assertTrue(self.scenario_execution_ros.process_results())
        self.assertGreater(sim_span, 1.8)
        self.assertLess(sim_span, 3.2)
        self.assertGreater(wall_span, 6.0, "a 2s wait at 0.25x realtime cannot be over in 2 host seconds")

    def test_timeout_modifier_counts_simulated_seconds(self):
        # A 1s timeout over a 10s wait fails after 1 simulated second, i.e. about 4 host seconds.
        self.rtf = 0.25
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_timeout:
    do serial:
        serial:
            wait elapsed(10s)
        with:
            timeout(1s)
        emit end
"""
        sim_before = self.sim_time
        wall_before = time.monotonic()
        self.execute(scenario_content)
        sim_span = self.sim_time - sim_before
        wall_span = time.monotonic() - wall_before

        self.assertGreater(sim_span, 0.9)
        self.assertLess(sim_span, 2.5)
        self.assertGreater(wall_span, 3.0, "a 1s timeout at 0.25x realtime cannot fire in 1 host second")
        self.assertLess(wall_span, 20.0, "the 10s wait must not have run to completion")

    def test_fails_loudly_when_clock_stalls(self):
        # The tree ticks on /clock, so a stopped clock stops the tree; the stall has to be
        # caught on host time or the run hangs.
        self.scenario_execution_ros.CLOCK_STALL_TIMEOUT = 2.0  # pylint: disable=invalid-name
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_stall:
    do serial:
        wait elapsed(100s)
        emit end
"""

        def stop_clock():
            time.sleep(1.5)
            self.publish_clock = False

        threading.Thread(target=stop_clock, daemon=True).start()
        wall_before = time.monotonic()
        self.execute(scenario_content)
        wall_span = time.monotonic() - wall_before

        self.assertFalse(self.scenario_execution_ros.process_results())
        self.assertLess(wall_span, 30.0, "a stalled /clock must not hang the run")

    def test_fails_loudly_on_backwards_jump(self):
        # A simulator reset underneath a running scenario.
        self.jump_back_at = 1.0
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_jump:
    do serial:
        wait elapsed(100s)
        emit end
"""
        wall_before = time.monotonic()
        self.execute(scenario_content)
        wall_span = time.monotonic() - wall_before

        self.assertFalse(self.scenario_execution_ros.process_results())
        self.assertLess(wall_span, 30.0)


class TestNoClockUnderSimTime(SimTimeFixture):
    # pylint: disable=missing-function-docstring

    def setUp(self):
        super().setUp()
        self.publish_clock = False  # nothing ever publishes /clock

    def test_fails_loudly_without_clock(self):
        self.scenario_execution_ros.CLOCK_WAIT_TIMEOUT = 2.0  # pylint: disable=invalid-name
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_no_clock:
    do serial:
        wait elapsed(1s)
        emit end
"""
        wall_before = time.monotonic()
        self.execute(scenario_content)
        wall_span = time.monotonic() - wall_before

        self.assertFalse(self.scenario_execution_ros.process_results())
        # The important half: the 1s wait did not quietly complete on host time.
        self.assertGreater(wall_span, 1.5)
        self.assertLess(wall_span, 20.0)


class TestHostTimeUnchanged(SimTimeFixture):
    """With use_sim_time off, a duration is what it has always been."""
    # pylint: disable=missing-function-docstring

    USE_SIM_TIME = False

    def test_wait_elapsed_counts_host_seconds(self):
        self.publish_clock = False  # no /clock at all, and none is needed
        scenario_content = """
import osc.ros
import osc.helpers

scenario test_host_time:
    do serial:
        wait elapsed(1s)
        emit end
"""
        wall_before = time.monotonic()
        self.execute(scenario_content)
        wall_span = time.monotonic() - wall_before

        self.assertTrue(self.scenario_execution_ros.process_results())
        # The span carries the run's own bring-up as well as the wait. What it says is that
        # the wait was really waited out, and that a run without /clock is not gated on one.
        self.assertGreater(wall_span, 1.0)
        self.assertLess(wall_span, 4.0)


if __name__ == '__main__':
    unittest.main()
