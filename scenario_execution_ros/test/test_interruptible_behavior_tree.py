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

import unittest

import py_trees
import rclpy

from scenario_execution_ros.scenario_execution_ros import InterruptibleBehaviorTree


class Counter(py_trees.behaviour.Behaviour):
    """Reports SUCCESS and counts its ticks, so a test can tell whether ticking stopped."""

    def __init__(self):
        super().__init__(name="counter")
        self.ticks = 0

    def update(self):
        self.ticks += 1
        return py_trees.common.Status.SUCCESS


class TestInterruptibleBehaviorTree(unittest.TestCase):
    """``interrupt()`` must actually stop the rclpy-timer ticking.

    py_trees' ``interrupt()`` only sets ``interrupt_tick_tocking``, and py_trees_ros' timer callback
    never reads it -- so on the plain class the ticks continue and a scenario that has asked to shut
    down keeps re-initialising its actions. That is what re-spawned ``ros2 launch`` during teardown
    and orphaned the simulator, losing the run's recording and capture.
    """

    @classmethod
    def setUpClass(cls):
        # rclpy's context is global, and a sibling test module in the same pytest run may already
        # own it. Only init (and only shut down) what this class actually brought up, or the two
        # collide: whichever ran second would fail on an already-initialised context, and whichever
        # shut down first would pull the context out from under the other.
        cls._owns_context = not rclpy.ok()
        if cls._owns_context:
            rclpy.init()

    @classmethod
    def tearDownClass(cls):
        if cls._owns_context:
            rclpy.shutdown()

    def setUp(self):
        self.node = rclpy.create_node("test_interruptible_behavior_tree")
        self.counter = Counter()
        self.tree = InterruptibleBehaviorTree(self.counter)
        self.tree.setup(node=self.node, timeout=10.0)
        self.addCleanup(self._teardown)

    def _teardown(self):
        # The tree adopts the node and destroys it in shutdown(); guard against a test that already
        # shut it down.
        try:
            self.tree.shutdown()
        except Exception:  # noqa: BLE001 - cleanup must not mask a test failure
            pass

    def _spin(self, seconds):
        end = self.node.get_clock().now().nanoseconds + seconds * 1e9
        while self.node.get_clock().now().nanoseconds < end:
            rclpy.spin_once(self.node, timeout_sec=0.01)

    def test_interrupt_stops_the_ticking(self):
        self.tree.tick_tock(period_ms=50.0)
        self._spin(0.3)
        self.assertGreater(self.counter.ticks, 0, "the tree should have been ticking")

        self.tree.interrupt()
        ticks_at_interrupt = self.counter.ticks
        self._spin(0.3)

        self.assertEqual(self.counter.ticks, ticks_at_interrupt,
                         "interrupt() must stop the tick timer; a tick after shutdown was requested "
                         "re-initialises actions and re-spawns their processes")

    def test_interrupt_still_sets_the_py_trees_flag(self):
        # The base-class contract has to keep working: a non-ROS tick_tock loop reads this flag.
        self.tree.tick_tock(period_ms=50.0)
        self.tree.interrupt()
        self.assertTrue(self.tree.interrupt_tick_tocking)

    def test_interrupt_before_tick_tock_is_a_noop(self):
        # `timer` is None until tick_tock() runs; interrupting then must not raise.
        self.assertIsNone(self.tree.timer)
        self.tree.interrupt()

    def test_shutdown_after_interrupt_is_safe(self):
        # shutdown() cancels and destroys the same timer; doing it after interrupt() must not raise.
        self.tree.tick_tock(period_ms=50.0)
        self._spin(0.1)
        self.tree.interrupt()
        self.tree.shutdown()
