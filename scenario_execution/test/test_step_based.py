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

"""Tests for step-based simulation support (SimulationInterface + SimulationClock)."""

import unittest
import py_trees
from antlr4.InputStream import InputStream

from scenario_execution.scenario_execution_base import ScenarioExecution
from scenario_execution.simulation import SimulationInterface, SimulationClock, WallClock
from scenario_execution.clock_behaviors import ClockTimer, ClockTimeout
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_to_py_tree import create_py_tree
from .common import DebugLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _CountingSim(SimulationInterface):
    """A minimal SimulationInterface that records every lifecycle call."""

    DT = 0.1

    def __init__(self):
        self.setup_calls = 0
        self.reset_calls = 0
        self.step_calls = 0
        self.shutdown_calls = 0

    @property
    def dt(self):
        return self.DT

    def setup(self, **kwargs):
        self.setup_calls += 1

    def reset(self):
        self.reset_calls += 1

    def step(self):
        self.step_calls += 1

    def shutdown(self):
        self.shutdown_calls += 1


class _FailingSetupSim(_CountingSim):
    """Raises during setup() to verify shutdown() still gets called."""

    def setup(self, **kwargs):
        super().setup(**kwargs)
        raise RuntimeError("intentional setup failure")


class _FailingStepSim(_CountingSim):
    """Raises on the 3rd step() call."""

    def step(self):
        super().step()
        if self.step_calls >= 3:
            raise RuntimeError("intentional step failure")


class _SimAccessBehavior(py_trees.behaviour.Behaviour):
    """Stores the simulation object it receives in setup() kwargs."""

    def __init__(self):
        super().__init__(name="SimAccessBehavior")
        self.received_simulation = None
        self.received_clock = None

    def setup(self, **kwargs):
        self.received_simulation = kwargs.get('simulation')
        self.received_clock = kwargs.get('clock')

    def update(self):
        return py_trees.common.Status.SUCCESS


def _make_scenario_execution(sim=None, logger=None):
    """Create a ScenarioExecution with a manually built behavior tree."""
    if logger is None:
        logger = DebugLogger("")
    se = ScenarioExecution(
        debug=False,
        log_model=False,
        live_tree=False,
        scenario_file='test.osc',
        output_dir="",
        logger=logger,
        simulation=sim,
    )
    return se


def _parse_and_run(scenario_content, sim=None):
    """Parse an inline OSC string and run it, returning (scenario_execution, logger)."""
    logger = DebugLogger("")
    parser = OpenScenario2Parser(logger)
    tree = py_trees.composites.Sequence(name="", memory=True)
    parsed_tree = parser.parse_input_stream(InputStream(scenario_content))
    model = parser.create_internal_model(parsed_tree, tree, "test.osc", False)
    tree = create_py_tree(model, tree, parser.logger, False)
    se = _make_scenario_execution(sim=sim, logger=logger)
    se.tree = tree
    se.run()
    return se, logger


# ---------------------------------------------------------------------------
# SimulationClock unit tests
# ---------------------------------------------------------------------------

class TestSimulationClock(unittest.TestCase):

    def test_initial_time_is_zero(self):
        clock = SimulationClock(dt=0.01)
        self.assertAlmostEqual(clock.now(), 0.0)

    def test_advance_increments_by_dt(self):
        clock = SimulationClock(dt=0.1)
        clock.advance()
        self.assertAlmostEqual(clock.now(), 0.1)
        clock.advance()
        self.assertAlmostEqual(clock.now(), 0.2)

    def test_reset_returns_to_zero(self):
        clock = SimulationClock(dt=0.05)
        clock.advance()
        clock.advance()
        clock.reset()
        self.assertAlmostEqual(clock.now(), 0.0)

    def test_invalid_dt_raises(self):
        with self.assertRaises(ValueError):
            SimulationClock(dt=0.0)
        with self.assertRaises(ValueError):
            SimulationClock(dt=-1.0)

    def test_dt_property(self):
        clock = SimulationClock(dt=0.002)
        self.assertAlmostEqual(clock.dt, 0.002)


# ---------------------------------------------------------------------------
# ClockTimer unit tests
# ---------------------------------------------------------------------------

class TestClockTimer(unittest.TestCase):

    def _run_timer(self, clock, duration, steps):
        """Run a ClockTimer for `steps` ticks and return the final status."""
        timer = ClockTimer(name="test_timer", duration=duration)
        timer.setup(clock=clock)
        timer.initialise()
        status = None
        for _ in range(steps):
            status = timer.update()
            if status == py_trees.common.Status.SUCCESS:
                break
        return status

    def test_timer_with_wallclock_default(self):
        """ClockTimer defaults to WallClock when no clock kwarg is provided."""
        timer = ClockTimer(name="t", duration=100.0)
        timer.setup()  # no clock kwarg → WallClock
        timer.initialise()
        status = timer.update()
        self.assertEqual(status, py_trees.common.Status.RUNNING)

    def test_timer_with_sim_clock_completes(self):
        clock = SimulationClock(dt=0.1)
        # Need 10 steps to cover 1.0 s
        timer = ClockTimer(name="t", duration=1.0)
        timer.setup(clock=clock)
        timer.initialise()
        for _ in range(9):
            status = timer.update()
            self.assertEqual(status, py_trees.common.Status.RUNNING)
            clock.advance()
        # 10th advance makes clock.now() == 1.0 == finish_time → SUCCESS
        clock.advance()
        status = timer.update()
        self.assertEqual(status, py_trees.common.Status.SUCCESS)

    def test_timer_zero_duration_succeeds_immediately(self):
        clock = SimulationClock(dt=0.1)
        timer = ClockTimer(name="t", duration=0.0)
        timer.setup(clock=clock)
        timer.initialise()
        status = timer.update()
        self.assertEqual(status, py_trees.common.Status.SUCCESS)

    def test_negative_duration_raises(self):
        with self.assertRaises(ValueError):
            ClockTimer(name="t", duration=-1.0)


# ---------------------------------------------------------------------------
# ClockTimeout unit tests
# ---------------------------------------------------------------------------

class TestClockTimeout(unittest.TestCase):

    def test_timeout_does_not_fire_before_deadline(self):
        clock = SimulationClock(dt=0.1)
        child = py_trees.behaviours.Running(name="child")
        timeout = ClockTimeout(child=child, name="timeout", duration=1.0)
        timeout.setup(clock=clock)
        timeout.initialise()
        child.setup()
        child.initialise()
        child.update()  # child is RUNNING
        # 5 steps: 0.5 s elapsed, no timeout yet
        for _ in range(5):
            clock.advance()
        status = timeout.update()
        self.assertEqual(status, py_trees.common.Status.RUNNING)

    def test_timeout_fires_after_deadline(self):
        clock = SimulationClock(dt=0.1)
        child = py_trees.behaviours.Running(name="child")
        timeout = ClockTimeout(child=child, name="timeout", duration=0.5)
        timeout.setup(clock=clock)
        timeout.initialise()
        child.setup()
        child.initialise()
        child.update()
        # Advance past the deadline
        for _ in range(6):
            clock.advance()
        status = timeout.update()
        self.assertEqual(status, py_trees.common.Status.FAILURE)

    def test_negative_duration_raises(self):
        child = py_trees.behaviours.Running(name="child")
        with self.assertRaises(ValueError):
            ClockTimeout(child=child, name="t", duration=-1.0)


# ---------------------------------------------------------------------------
# SimulationInterface lifecycle integration tests
# ---------------------------------------------------------------------------

class TestSimulationLifecycle(unittest.TestCase):

    def _build_instant_scenario(self, sim):
        """Build a ScenarioExecution that succeeds immediately."""
        se = _make_scenario_execution(sim=sim)
        success_behavior = py_trees.behaviours.Success(name="done")
        se.tree = success_behavior
        return se

    def test_lifecycle_order(self):
        """setup → reset → step(s) → shutdown are all called in order."""
        sim = _CountingSim()
        se = self._build_instant_scenario(sim)
        se.run()
        self.assertEqual(sim.setup_calls, 1)
        self.assertEqual(sim.reset_calls, 1)
        self.assertGreaterEqual(sim.step_calls, 1)
        self.assertEqual(sim.shutdown_calls, 1)

    def test_shutdown_called_on_setup_failure(self):
        """shutdown() must NOT be called when setup() raises (sim was never ready)."""
        sim = _FailingSetupSim()
        se = self._build_instant_scenario(sim)
        se.run()
        self.assertEqual(sim.setup_calls, 1)
        self.assertEqual(sim.shutdown_calls, 0)  # sim never launched — nothing to shut down
        # Scenario result should indicate failure
        self.assertFalse(se.process_results())

    def test_shutdown_called_after_success(self):
        sim = _CountingSim()
        se = self._build_instant_scenario(sim)
        se.run()
        self.assertEqual(sim.shutdown_calls, 1)
        self.assertTrue(se.process_results())

    def test_simulation_passed_to_behaviors(self):
        """Behaviors receive simulation and clock via setup() kwargs."""
        sim = _CountingSim()
        se = _make_scenario_execution(sim=sim)
        accessor = _SimAccessBehavior()
        se.tree = accessor
        se.run()
        self.assertIs(accessor.received_simulation, sim)
        self.assertIsInstance(accessor.received_clock, SimulationClock)

    def test_step_count_matches_ticks(self):
        """step() is called exactly once per behavior-tree tick."""
        sim = _CountingSim()
        # A sequence that succeeds after exactly 5 ticks using a manual counter
        tick_count = [0]

        class CountingBehavior(py_trees.behaviour.Behaviour):
            def __init__(self):
                super().__init__(name="counter")

            def update(self):
                tick_count[0] += 1
                if tick_count[0] >= 5:
                    return py_trees.common.Status.SUCCESS
                return py_trees.common.Status.RUNNING

        se = _make_scenario_execution(sim=sim)
        se.tree = CountingBehavior()
        se.run()
        self.assertEqual(sim.step_calls, tick_count[0])


# ---------------------------------------------------------------------------
# OSC wait elapsed() with simulation clock
# ---------------------------------------------------------------------------

class TestWaitElapsedWithSimClock(unittest.TestCase):

    def test_wait_elapsed_completes_after_correct_steps(self):
        """wait elapsed(0.5s) with dt=0.1 should take exactly 5 sim steps."""
        sim = _CountingSim()  # dt=0.1

        scenario_content = """
type time is SI(s: 1)
unit s          of time is SI(s: 1, factor: 1)

scenario test:
    do serial:
        wait elapsed(0.5s)
"""
        se, logger = _parse_and_run(scenario_content, sim=sim)
        self.assertTrue(se.process_results())
        # 0.5 s / 0.1 dt = 5 steps to reach the deadline, plus the tick that detects SUCCESS
        self.assertGreaterEqual(sim.step_calls, 5)

    def test_wait_elapsed_without_sim_uses_wallclock(self):
        """Without a simulation, wait elapsed uses wall clock and the test still passes."""
        scenario_content = """
type time is SI(s: 1)
unit s          of time is SI(s: 1, factor: 1)

scenario test:
    do serial:
        wait elapsed(0.01s)
"""
        se, logger = _parse_and_run(scenario_content, sim=None)
        self.assertTrue(se.process_results())


if __name__ == '__main__':
    unittest.main()
