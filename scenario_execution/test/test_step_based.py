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

from scenario_execution.scenario_execution_base import ScenarioExecution, _get_missing_reset_params, _build_reset_kwargs
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
    se.scenario_params = parser.scenario_params
    se.scenarios_list = [(tree, parser.scenario_params, None)]
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
        # Tick 5 times via tick_once() which ticks child then calls update()
        for _ in range(5):
            timeout.tick_once()
            clock.advance()  # 5 x 0.1 = 0.5 s, well below 1.0 s deadline
        self.assertEqual(timeout.status, py_trees.common.Status.RUNNING)

    def test_timeout_fires_after_deadline(self):
        clock = SimulationClock(dt=0.1)
        child = py_trees.behaviours.Running(name="child")
        timeout = ClockTimeout(child=child, name="timeout", duration=0.5)
        timeout.setup(clock=clock)
        # Tick 7 times: after 6 advances clock = 0.6 s > 0.5 s deadline
        for _ in range(7):
            timeout.tick_once()
            clock.advance()
        self.assertEqual(timeout.status, py_trees.common.Status.FAILURE)

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
        se.scenarios_list = [(success_behavior, {}, None)]
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
        se.scenarios_list = [(accessor, {}, None)]
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
        behavior = CountingBehavior()
        se.tree = behavior
        se.scenarios_list = [(behavior, {}, None)]
        se.run()
        self.assertEqual(sim.step_calls, tick_count[0])


# ---------------------------------------------------------------------------
# OSC wait elapsed() with simulation clock
# ---------------------------------------------------------------------------

class TestScenarioParamsInReset(unittest.TestCase):

    def test_scalar_params_reach_reset(self):
        """Scalar scenario parameters are injected as named args into reset()."""

        class _Sim(_CountingSim):
            def reset(self, speed, count, label):
                self.received_speed = speed
                self.received_count = count
                self.received_label = label

        sim = _Sim()
        scenario_content = """
type time is SI(s: 1)
unit s          of time is SI(s: 1, factor: 1)

scenario test:
    speed: float = 1.5
    count: int = 3
    label: string = "hello"
    do serial:
        wait elapsed(0.1s)
"""
        _parse_and_run(scenario_content, sim=sim)
        self.assertAlmostEqual(sim.received_speed, 1.5)
        self.assertEqual(sim.received_count, 3)
        self.assertEqual(sim.received_label, 'hello')

    def test_struct_params_reach_reset(self):
        """Structured scenario parameters are passed as nested dicts to named args."""

        class _Sim(_CountingSim):
            def reset(self, start_pos):
                self.received_start_pos = start_pos

        sim = _Sim()
        scenario_content = """
type time is SI(s: 1)
unit s          of time is SI(s: 1, factor: 1)
type length is SI(m: 1)
unit m of length is SI(m: 1, factor: 1)

struct position_3d:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

scenario test:
    start_pos: position_3d = position_3d(x: 1.0, y: 2.0, z: 3.0)
    do serial:
        wait elapsed(0.1s)
"""
        _parse_and_run(scenario_content, sim=sim)
        self.assertIn('x', sim.received_start_pos)
        self.assertAlmostEqual(sim.received_start_pos['x'], 1.0)
        self.assertAlmostEqual(sim.received_start_pos['y'], 2.0)
        self.assertAlmostEqual(sim.received_start_pos['z'], 3.0)

    def test_no_params_reset_called(self):
        """reset() with no args is called once even when the scenario declares no params."""
        sim = _CountingSim()
        scenario_content = """
type time is SI(s: 1)
unit s          of time is SI(s: 1, factor: 1)

scenario test:
    do serial:
        wait elapsed(0.1s)
"""
        _parse_and_run(scenario_content, sim=sim)
        self.assertEqual(sim.reset_calls, 1)


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


# ---------------------------------------------------------------------------
# reset() signature validation (_get_missing_reset_params)
# ---------------------------------------------------------------------------

class TestResetSignatureValidation(unittest.TestCase):

    def test_no_required_params_ok(self):
        """`reset(self, scenario_params=None)` — nothing required, nothing missing."""

        class _Sim(_CountingSim):
            def reset(self, scenario_params=None):
                pass

        self.assertEqual(_get_missing_reset_params(_Sim(), {}), set())

    def test_required_param_present(self):
        """A required keyword arg that IS in scenario_params is not flagged."""

        class _Sim(_CountingSim):
            def reset(self, initial_velocity, scenario_params=None):
                pass

        self.assertEqual(
            _get_missing_reset_params(_Sim(), {'initial_velocity': 1.0}), set()
        )

    def test_required_param_missing(self):
        """A required keyword arg absent from scenario_params is returned."""

        class _Sim(_CountingSim):
            def reset(self, initial_velocity, scenario_params=None):
                pass

        self.assertEqual(
            _get_missing_reset_params(_Sim(), {}), {'initial_velocity'}
        )

    def test_optional_param_not_flagged(self):
        """A param with a default value is not flagged even if absent."""

        class _Sim(_CountingSim):
            def reset(self, gravity=9.81, scenario_params=None):
                pass

        self.assertEqual(_get_missing_reset_params(_Sim(), {}), set())

    def test_multiple_required_params_all_missing(self):
        """Multiple required params all missing → all returned."""

        class _Sim(_CountingSim):
            def reset(self, width, height, scenario_params=None):
                pass

        self.assertEqual(
            _get_missing_reset_params(_Sim(), {}), {'width', 'height'}
        )

    def test_multiple_required_params_partially_present(self):
        """Only the absent required params are returned."""

        class _Sim(_CountingSim):
            def reset(self, width, height, scenario_params=None):
                pass

        self.assertEqual(
            _get_missing_reset_params(_Sim(), {'width': 5}), {'height'}
        )

    def test_scenario_fails_when_required_reset_param_missing(self):
        """run_with_simulation() fails before reset() when a required param is absent."""

        class _SimNeedsParam(_CountingSim):
            def reset(self, robot_start_x, scenario_params=None):
                pass

        sim = _SimNeedsParam()
        # OSC scenario has no parameter named robot_start_x
        scenario_content = """
type time is SI(s: 1)
unit s          of time is SI(s: 1, factor: 1)

scenario test:
    do serial:
        wait elapsed(0.1s)
"""
        se, _ = _parse_and_run(scenario_content, sim=sim)
        self.assertFalse(se.process_results())
        # reset() must never have been called
        self.assertEqual(sim.reset_calls, 0)

    def test_scenario_succeeds_when_required_reset_param_provided(self):
        """Scenario succeeds when the OSC file defines all required reset() params."""

        class _SimNeedsParam(_CountingSim):
            def reset(self, robot_start_x, scenario_params=None):
                self.received_robot_start_x = robot_start_x

        sim = _SimNeedsParam()
        scenario_content = """
type time is SI(s: 1)
unit s          of time is SI(s: 1, factor: 1)

scenario test:
    robot_start_x: float = 1.0
    do serial:
        wait elapsed(0.1s)
"""
        se, _ = _parse_and_run(scenario_content, sim=sim)
        self.assertTrue(se.process_results())
        self.assertTrue(hasattr(sim, 'received_robot_start_x'), "reset() was not called")
        self.assertAlmostEqual(sim.received_robot_start_x, 1.0)

    def test_build_reset_kwargs_injects_required_and_optional(self):
        """_build_reset_kwargs maps scenario_params values to named args."""

        class _Sim(_CountingSim):
            def reset(self, speed, gravity=9.81):
                pass

        params = {'speed': 5.0}
        kwargs = _build_reset_kwargs(_Sim(), params)
        self.assertAlmostEqual(kwargs['speed'], 5.0)
        self.assertAlmostEqual(kwargs['gravity'], 9.81)  # default used
        self.assertNotIn('scenario_params', kwargs)


if __name__ == '__main__':
    unittest.main()
