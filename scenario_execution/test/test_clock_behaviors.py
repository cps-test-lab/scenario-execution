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

"""Tests for the clock-aware timers and for the two time domains they read.

Every case here drives a clock the test controls, so a duration is asserted without
any of it being waited out: that a timer counts its clock and not the host is the
property under test, and a test that slept would be asserting the opposite.
"""

import unittest
import py_trees

from scenario_execution.simulation import Clock, WallClock, HostClock, SimulationClock
from scenario_execution.clock_behaviors import ClockTimer, ClockTimeout


class FakeClock(Clock):
    """A clock the test moves by hand."""

    def __init__(self, start=0.0):
        self.time = start

    def now(self) -> float:
        return self.time


class AlwaysRunning(py_trees.behaviour.Behaviour):

    def update(self):
        return py_trees.common.Status.RUNNING


class TestHostClock(unittest.TestCase):

    def test_zero_based(self):
        self.assertAlmostEqual(HostClock().now(), 0.0, places=2)

    def test_non_decreasing(self):
        clock = HostClock()
        self.assertLessEqual(clock.now(), clock.now())


class TestClockTimer(unittest.TestCase):

    def test_counts_its_clock_not_the_host(self):
        clock = FakeClock(10.0)
        timer = ClockTimer(name="wait 2s", duration=2.0)
        timer.setup(clock=clock)
        timer.initialise()

        self.assertEqual(timer.update(), py_trees.common.Status.RUNNING)
        clock.time = 11.9
        self.assertEqual(timer.update(), py_trees.common.Status.RUNNING)
        clock.time = 12.0
        self.assertEqual(timer.update(), py_trees.common.Status.SUCCESS)

    def test_initialise_rebases_the_deadline(self):
        clock = FakeClock(0.0)
        timer = ClockTimer(name="wait 1s", duration=1.0)
        timer.setup(clock=clock)

        timer.initialise()
        clock.time = 1.0
        self.assertEqual(timer.update(), py_trees.common.Status.SUCCESS)

        clock.time = 100.0
        timer.initialise()
        self.assertEqual(timer.update(), py_trees.common.Status.RUNNING)
        clock.time = 101.0
        self.assertEqual(timer.update(), py_trees.common.Status.SUCCESS)

    def test_falls_back_to_wall_clock_without_a_clock_kwarg(self):
        timer = ClockTimer(name="wait 1s", duration=1.0)
        timer.setup()
        self.assertIsInstance(timer._clock, WallClock)  # pylint: disable=protected-access

    def test_rejects_a_negative_duration(self):
        with self.assertRaises(ValueError):
            ClockTimer(name="wait", duration=-1.0)


class TestClockTimeout(unittest.TestCase):

    def test_fails_the_child_on_its_clock(self):
        clock = FakeClock(0.0)
        child = AlwaysRunning(name="child")
        timeout = ClockTimeout(child=child, name="timeout", duration=5.0)
        timeout.setup(clock=clock)

        def tick():
            for _ in timeout.tick():
                pass
            return timeout.status

        self.assertEqual(tick(), py_trees.common.Status.RUNNING)
        clock.time = 5.0
        self.assertEqual(tick(), py_trees.common.Status.RUNNING)
        clock.time = 5.1
        self.assertEqual(tick(), py_trees.common.Status.FAILURE)
        self.assertEqual(child.status, py_trees.common.Status.INVALID)

    def test_falls_back_to_wall_clock_without_a_clock_kwarg(self):
        timeout = ClockTimeout(child=AlwaysRunning(name="child"), name="timeout", duration=1.0)
        timeout.setup()
        self.assertIsInstance(timeout._clock, WallClock)  # pylint: disable=protected-access


class TestClocksAreZeroBased(unittest.TestCase):
    """The contract the recorders rely on: a timestamp is an offset into the scenario."""

    def test_simulation_clock(self):
        self.assertEqual(SimulationClock(0.1).now(), 0.0)

    def test_host_clock(self):
        self.assertAlmostEqual(HostClock().now(), 0.0, places=2)

    def test_wall_clock_is_not_zero_based(self):
        # Which is why the wall-clock runner passes no clock at all, and the timers fall
        # back to this one only as a bare time source.
        self.assertGreater(WallClock().now(), 0.0)


if __name__ == '__main__':
    unittest.main()
