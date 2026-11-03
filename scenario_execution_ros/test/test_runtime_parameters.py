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
Test that runtime parameters reach the base class from the ROS runner.
"""
import sys
import unittest

import rclpy

from scenario_execution.utils import tick_recorder
from scenario_execution_ros.scenario_execution_ros import ROSScenarioExecution


class TestRuntimeParameters(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self):
        rclpy.init()
        self.argv = sys.argv

    def tearDown(self):
        sys.argv = self.argv
        rclpy.try_shutdown()

    def build(self, *args):
        sys.argv = ["scenario_execution_ros", *args, "test.osc"]
        return ROSScenarioExecution()

    def test_step_duration_reaches_the_tick_period(self):
        """It used to be parsed and dropped, leaving the period silently at its default.

        Everything derived from the tick rate divides by this number, so it has to be
        the value that was actually asked for.
        """
        self.assertEqual(self.build("--step-duration", "0.05").tick_period, 0.05)

    def test_step_duration_defaults_when_not_given(self):
        self.assertEqual(self.build().tick_period, 0.1)

    def test_tick_log_reaches_the_base_class(self):
        self.assertFalse(self.build().tick_log)
        self.assertTrue(self.build("--tick-log").tick_log)

    def test_driver_is_the_ros_timer(self):
        """The tree is ticked by an rclpy timer, and a record has to say so."""
        self.assertEqual(self.build().tick_driver, tick_recorder.DRIVER_ROS_TIMER)


if __name__ == '__main__':
    unittest.main()
