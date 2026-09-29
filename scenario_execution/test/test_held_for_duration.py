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

"""The documented pattern for "a condition has held for a duration".

Time is a step-based simulation clock, so each scenario runs unpaced and the tick at which it ends
is exact: the step count is the scenario time in units of ``dt``.
"""

import unittest
from pathlib import Path

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution.scenario_execution_base import ScenarioExecution
from scenario_execution.simulation import SimulationInterface
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_blackboard import create_py_tree_blackboard
from scenario_execution.model.model_to_py_tree import create_py_tree
from .common import DebugLogger

EXAMPLE = Path(__file__).resolve().parents[2] / 'examples' / 'example_scenario' / 'held_for_duration.osc'


class _SteppedSim(SimulationInterface):
    """Advances the scenario clock by ``dt`` per tick and counts the ticks."""

    def __init__(self):
        self.steps = 0

    @property
    def dt(self):
        return 0.1

    def setup(self, **kwargs):
        pass

    def reset(self, **kwargs):
        pass

    def step(self):
        self.steps += 1

    def shutdown(self):
        pass


def scenario(driver, retries=10, deadline='10s'):
    """The pattern with a 2 s hold on ``close == 1``, beside a *driver* branch that sets ``close``.

    The driver runs in a ``one_of`` and never finishes on its own, so the scenario ends exactly
    when the pattern does.
    """
    return f"""
import osc.helpers

scenario test:
    var close: int = 0
    do one_of:
        serial:
{driver}
            wait elapsed(100s)
        serial:
            serial:
                wait close == 1
                one_of:
                    wait elapsed(2s)
                    serial:
                        wait close == 0
                    with:
                        success_is_failure()
            with:
                retry({retries})
        with:
            timeout({deadline})
"""


class TestHeldForDuration(unittest.TestCase):
    """Succeeds once the condition has held for a full duration without a break."""
    # pylint: disable=missing-function-docstring

    def run_scenario(self, content):
        logger = DebugLogger("")
        parser = OpenScenario2Parser(logger)
        tree = py_trees.composites.Sequence(name="", memory=True)
        model = parser.create_internal_model(parser.parse_input_stream(InputStream(content)), tree, "test.osc", False)
        create_py_tree_blackboard(model, tree, parser.logger, False)
        tree = create_py_tree(model, tree, parser.logger, False)
        sim = _SteppedSim()
        execution = ScenarioExecution(debug=False, log_model=False, live_tree=False, scenario_file='test.osc',
                                      output_dir="", logger=logger, simulation=sim)
        execution.scenarios_list = [(tree, parser.scenario_params, None)]
        execution.run()
        return execution.process_results(), sim.steps * sim.dt

    def assert_ends_near(self, ended, expected):
        # The pattern reacts on the tick after a change, so it ends within a few ticks of it.
        self.assertGreaterEqual(ended, expected)
        self.assertLess(ended, expected + 0.35)

    def test_condition_held_for_the_duration_succeeds(self):
        # close from 1 s on, never broken: done 2 s later.
        success, ended = self.run_scenario(scenario("""\
            wait elapsed(1s)
            increment(close)"""))
        self.assertTrue(success)
        self.assert_ends_near(ended, 3.0)

    def test_a_break_restarts_the_timer(self):
        # close at 1 s, broken at 2 s, close again at 2.5 s: the first second of holding does not
        # count, so success comes a full 2 s after 2.5 s -- not at 3 s, and not at 3.5 s.
        success, ended = self.run_scenario(scenario("""\
            wait elapsed(1s)
            increment(close)
            wait elapsed(1s)
            decrement(close)
            wait elapsed(0.5s)
            increment(close)"""))
        self.assertTrue(success)
        self.assert_ends_near(ended, 4.5)

    def test_condition_that_never_holds_times_out(self):
        success, ended = self.run_scenario(scenario("""\
            wait elapsed(1s)""", deadline='5s'))
        self.assertFalse(success)
        self.assert_ends_near(ended, 5.0)

    def test_condition_that_never_holds_long_enough_times_out(self):
        # Held for 1.5 s at a time, broken for 0.5 s, over and over: never a full 2 s.
        blink = "\n".join(["""\
            wait elapsed(0.5s)
            increment(close)
            wait elapsed(1.5s)
            decrement(close)"""] * 5)
        success, ended = self.run_scenario(scenario(blink, retries=100, deadline='9s'))
        self.assertFalse(success)
        self.assert_ends_near(ended, 9.0)

    def test_more_breaks_than_the_retry_count_fail(self):
        # retry(2) permits one break: the second break ends the pattern in failure, at 4 s.
        blink = "\n".join(["""\
            wait elapsed(0.5s)
            increment(close)
            wait elapsed(1.5s)
            decrement(close)"""] * 5)
        success, ended = self.run_scenario(scenario(blink, retries=2))
        self.assertFalse(success)
        self.assert_ends_near(ended, 4.0)

    def test_the_example_ends_after_the_second_hold(self):
        # The example the documentation includes: close at 1 s, broken at 2 s, close again at 2.5 s.
        success, ended = self.run_scenario(EXAMPLE.read_text(encoding='utf-8'))
        self.assertTrue(success)
        self.assert_ends_near(ended, 4.5)


if __name__ == '__main__':
    unittest.main()
