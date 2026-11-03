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
Run a real scenario with and without --tick-log, through the plain runner.
"""
import csv
import json
import os
import tempfile
import unittest

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution import ScenarioExecution
from scenario_execution.simulation import SimulationInterface
from scenario_execution.model.model_blackboard import create_py_tree_blackboard
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution import tick_report
from scenario_execution.utils import bt_logger, tick_recorder
from scenario_execution.utils.logging import Logger

SCENARIO = """
import osc.helpers

scenario test:
    do serial:
        wait elapsed(0.3s)
        emit end
"""


class SteppedSim(SimulationInterface):
    """Minimal step-based simulation: scenario execution drives the clock itself."""

    DT = 0.05

    def __init__(self):
        self.steps = 0

    @property
    def dt(self):
        return self.DT

    def setup(self, **kwargs):
        pass

    def reset(self, **kwargs):
        pass

    def step(self):
        self.steps += 1

    def shutdown(self):
        pass


class TestTickLogEndToEnd(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def run_scenario(self, **kwargs):
        parser = OpenScenario2Parser(Logger('test', False))
        tree = py_trees.composites.Sequence(name="", memory=True)
        parsed = parser.parse_input_stream(InputStream(SCENARIO))
        model = parser.create_internal_model(parsed, tree, "test.osc", False)
        create_py_tree_blackboard(model, tree, parser.logger, False)
        tree = create_py_tree(model, tree, parser.logger, False)
        execution = ScenarioExecution(debug=False, log_model=False, live_tree=False,
                                      scenario_file='test.osc', output_dir=self.dir,
                                      tick_period=0.05, **kwargs)
        execution.scenarios_list = [(tree, {}, None)]
        execution.run()
        return execution

    def run_summary(self, **kwargs):
        self.run_scenario(**kwargs)
        return tick_report.summarize(self.dir)

    def read(self, filename):
        with open(os.path.join(self.dir, filename), encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_without_the_flag_nothing_is_written(self):
        self.run_scenario()
        self.assertFalse(os.path.exists(os.path.join(self.dir, tick_recorder.TICK_FILENAME)))
        self.assertFalse(os.path.exists(os.path.join(self.dir, tick_recorder.ACTION_FILENAME)))

    def test_records_a_real_run(self):
        self.run_scenario(tick_log=True)
        ticks = self.read(tick_recorder.TICK_FILENAME)
        actions = self.read(tick_recorder.ACTION_FILENAME)
        # ~0.3s of scenario at a 0.05s period, so several ticks; the exact count
        # depends on the machine, which is the whole reason it is being recorded.
        self.assertGreater(len(ticks), 2)
        self.assertEqual([row["driver"] for row in ticks],
                         [tick_recorder.DRIVER_WALL_LOOP] * len(ticks))
        self.assertEqual({row["period_s"] for row in ticks}, {"0.050000"})
        self.assertEqual([int(row["tick"]) for row in ticks],
                         list(range(1, len(ticks) + 1)))
        self.assertTrue(actions)
        self.assertTrue(all(row["behavior_name"] for row in actions),
                        "readable on its own: every row names its action")

    def test_action_time_is_contained_by_its_tick(self):
        self.run_scenario(tick_log=True)
        durations = {row["tick"]: float(row["duration_s"])
                     for row in self.read(tick_recorder.TICK_FILENAME)}
        spent = {}
        for row in self.read(tick_recorder.ACTION_FILENAME):
            if row["phase"] != tick_recorder.PHASE_UPDATE:
                continue
            spent[row["tick"]] = spent.get(row["tick"], 0.0) + float(row["duration_s"])
        self.assertTrue(spent)
        for tick, total in spent.items():
            self.assertLessEqual(total, durations[tick] + 1e-9,
                                 f"tick {tick} does not account for its actions")

    def test_joins_the_behaviour_tree_log_when_both_are_enabled(self):
        self.run_scenario(tick_log=True, bt_log=True)
        with open(os.path.join(self.dir, bt_logger.DEFAULT_FILENAME), encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle][1:]
        by_id = {record["behavior_id"]: record for record in records if "behavior_id" in record}
        actions = self.read(tick_recorder.ACTION_FILENAME)
        self.assertTrue(actions)
        for row in actions:
            self.assertIn(row["behavior_id"], by_id,
                          "identity must be spelled the same way in both files")
            self.assertEqual(row["behavior_name"], by_id[row["behavior_id"]]["behavior_name"])
            self.assertEqual(row["class_name"], by_id[row["behavior_id"]]["class_name"])

    def test_step_based_simulation_is_recorded(self):
        """Scenario execution stepping the simulation is the third tick driver.

        The period comes from the simulation's dt rather than from --step-duration,
        and timestamp advances by exactly that, because the scenario's clock is the
        simulation's.
        """
        sim = SteppedSim()
        self.run_scenario(tick_log=True, simulation=sim)
        ticks = self.read(tick_recorder.TICK_FILENAME)
        self.assertEqual(len(ticks), sim.steps, "one row per step")
        self.assertEqual({row["driver"] for row in ticks}, {tick_recorder.DRIVER_SIM_STEP})
        self.assertEqual({row["period_s"] for row in ticks}, {"0.050000"},
                         "the simulation's dt governs the period, not --step-duration")
        self.assertEqual([row["timestamp"] for row in ticks[:3]],
                         ["0.050000", "0.100000", "0.150000"])
        self.assertTrue(self.read(tick_recorder.ACTION_FILENAME),
                        "the drill-down still works when the clock is not real")

    def test_step_based_summary_offers_no_ratio(self):
        """The loop is unpaced, so there is no rate to hold and none is claimed.

        Reporting interval_s against dt here would say the run was many times
        faster than intended, which is not a statement about anything.
        """
        summary = " ".join(self.run_summary(tick_log=True, simulation=SteppedSim()))
        self.assertIn("unpaced", summary)
        self.assertNotIn("late", summary)
        self.assertNotIn("x the configured period", summary)

    def test_tick_log_without_output_dir_is_refused(self):
        parser = OpenScenario2Parser(Logger('test', False))
        tree = py_trees.composites.Sequence(name="", memory=True)
        parsed = parser.parse_input_stream(InputStream(SCENARIO))
        model = parser.create_internal_model(parsed, tree, "test.osc", False)
        create_py_tree_blackboard(model, tree, parser.logger, False)
        tree = create_py_tree(model, tree, parser.logger, False)
        execution = ScenarioExecution(debug=False, log_model=False, live_tree=False,
                                      scenario_file='test.osc', output_dir='',
                                      tick_period=0.05, tick_log=True)
        self.assertRaises(ValueError, execution.setup, tree)


if __name__ == '__main__':
    unittest.main()
