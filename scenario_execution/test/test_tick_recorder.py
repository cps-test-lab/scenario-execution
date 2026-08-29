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
Test the tick and action timing records (--tick-log)
"""
import csv
import os
import tempfile
import time
import unittest

import py_trees

from scenario_execution.actions.base_action import BaseAction
from scenario_execution.simulation import Clock
from scenario_execution.utils import tick_recorder
from scenario_execution.utils.tick_recorder import TickRecorder


class FakeClock(Clock):
    """A clock the test advances by hand, standing in for a SimulationClock."""

    def __init__(self):
        self.value = 0.0

    def now(self) -> float:
        return self.value


class Waiter(BaseAction):
    """RUNNING for *ticks* ticks, then SUCCESS, optionally burning wall time."""

    def __init__(self, ticks=3, sleep=0.0):
        super().__init__()
        self.remaining = ticks
        self.sleep = sleep

    def update(self):
        if self.sleep:
            time.sleep(self.sleep)
        self.remaining -= 1
        if self.remaining <= 0:
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.RUNNING


def make_action(name, ticks=3, sleep=0.0):
    action = Waiter(ticks=ticks, sleep=sleep)
    action.name = name
    return action


class RecorderTestCase(unittest.TestCase):
    """Shared fixture: a temporary output directory and a tree wired to a recorder."""
    # pylint: disable=missing-function-docstring

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, root, clock=None, driver=tick_recorder.DRIVER_WALL_LOOP, period=0.1):
        tree = py_trees.trees.BehaviourTree(root)
        recorder = TickRecorder(self.dir, period, driver, clock=clock)
        recorder.install_on_tree(tree)
        recorder.watch_tree_updates(tree)
        tree.add_pre_tick_handler(recorder.pre_tick_handler)
        tree.add_post_tick_handler(recorder)
        return tree, recorder

    def read(self, filename):
        with open(os.path.join(self.dir, filename), encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def ticks(self):
        return self.read(tick_recorder.TICK_FILENAME)

    def actions(self):
        return self.read(tick_recorder.ACTION_FILENAME)


class TestTickRecords(RecorderTestCase):
    """The files exist and say something even when nothing happened."""
    # pylint: disable=missing-function-docstring

    def test_headers_written_before_any_tick(self):
        """A run whose tree never ticked is measured and empty, not unmeasured."""
        _, recorder = self.build(make_action("a"))
        recorder.close()
        self.assertEqual(self.ticks(), [])
        self.assertEqual(self.actions(), [])
        with open(os.path.join(self.dir, tick_recorder.TICK_FILENAME), encoding="utf-8") as handle:
            self.assertEqual(handle.readline().strip(), ",".join(tick_recorder.TICK_FIELDS))
        with open(os.path.join(self.dir, tick_recorder.ACTION_FILENAME), encoding="utf-8") as handle:
            self.assertEqual(handle.readline().strip(), ",".join(tick_recorder.ACTION_FIELDS))

    def test_close_flushes_the_last_rows(self):
        """Rows buffered since the last flush must survive the end of the run."""
        tree, recorder = self.build(make_action("a", ticks=10))
        tree.tick()
        self.assertEqual(self.ticks(), [], "not yet flushed")
        recorder.close()
        self.assertEqual(len(self.ticks()), 1)

    def test_tick_row_fields(self):
        tree, recorder = self.build(make_action("a", ticks=10), period=0.05)
        tree.tick()
        tree.tick()
        recorder.close()
        rows = self.ticks()
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["tick"] for row in rows], ["1", "2"])
        self.assertEqual(rows[0]["interval_s"], "", "no preceding tick to measure against")
        self.assertGreater(float(rows[1]["interval_s"]), 0.0)
        self.assertEqual({row["period_s"] for row in rows}, {"0.050000"})
        self.assertEqual({row["driver"] for row in rows}, {tick_recorder.DRIVER_WALL_LOOP})
        for row in rows:
            self.assertGreaterEqual(float(row["duration_s"]), 0.0)
            self.assertGreater(float(row["wall_ts"]), 1.0e9, "wall_ts is epoch-valued")

    def test_timestamp_follows_the_supplied_clock(self):
        """Same definition as the behaviour-tree log, so the records line up."""
        clock = FakeClock()
        tree, recorder = self.build(make_action("a", ticks=10), clock=clock)
        clock.value = 1.5
        tree.tick()
        clock.value = 3.25
        tree.tick()
        recorder.close()
        self.assertEqual([row["timestamp"] for row in self.ticks()],
                         ["1.500000", "3.250000"])

    def test_driver_is_recorded(self):
        tree, recorder = self.build(make_action("a", ticks=10),
                                    driver=tick_recorder.DRIVER_SIM_STEP)
        tree.tick()
        recorder.close()
        self.assertEqual(self.ticks()[0]["driver"], tick_recorder.DRIVER_SIM_STEP)


class TestActionRecords(RecorderTestCase):
    """Which node spent the time inside a tick."""
    # pylint: disable=missing-function-docstring

    def test_setup_execute_and_update_phases(self):
        root = make_action("a", ticks=2)
        tree, recorder = self.build(root)
        tree.setup()
        tree.tick()
        tree.tick()
        recorder.close()
        phases = [row["phase"] for row in self.actions()]
        self.assertEqual(phases.count(tick_recorder.PHASE_SETUP), 1)
        self.assertEqual(phases.count(tick_recorder.PHASE_EXECUTE), 1,
                         "one activation, so one execute row")
        self.assertEqual(phases.count(tick_recorder.PHASE_UPDATE), 2)

    def test_identity_matches_the_behaviour_tree_log_spelling(self):
        root = make_action("drive")
        tree, recorder = self.build(root)
        tree.tick()
        recorder.close()
        rows = self.actions()
        for row in rows:
            self.assertEqual(row["behavior_id"], str(root.id))
            self.assertEqual(row["behavior_name"], "drive")
            self.assertEqual(row["class_name"],
                             py_trees.utilities.get_fully_qualified_name(root))
        by_phase = {row["phase"]: row["status"] for row in rows}
        # py_trees assigns the status only after update() returns, so the wrapper has
        # to take it from the return value -- otherwise every first tick reads INVALID.
        self.assertEqual(by_phase[tick_recorder.PHASE_UPDATE], "RUNNING")
        self.assertEqual(by_phase[tick_recorder.PHASE_EXECUTE], "INVALID",
                         "initialise() runs before the action has a status")

    def test_setup_rows_have_no_tick(self):
        """Bring-up happens before the first tick, so there is no tick to belong to."""
        tree, recorder = self.build(make_action("a"))
        tree.setup()
        tree.tick()
        recorder.close()
        rows = self.actions()
        setup_rows = [row for row in rows if row["phase"] == tick_recorder.PHASE_SETUP]
        self.assertTrue(setup_rows)
        self.assertEqual({row["tick"] for row in setup_rows}, {""})
        update_rows = [row for row in rows if row["phase"] == tick_recorder.PHASE_UPDATE]
        self.assertEqual({row["tick"] for row in update_rows}, {"1"})

    def test_rows_only_for_actions_that_were_ticked(self):
        """A branch the tree never reaches has no rows -- it did not run at all."""
        first = make_action("first", ticks=5)
        second = make_action("second", ticks=5)
        tree, recorder = self.build(py_trees.composites.Sequence("seq", False, [first, second]))
        tree.tick()
        recorder.close()
        names = {row["behavior_name"] for row in self.actions()}
        self.assertEqual(names, {"first"})

    def test_action_durations_are_contained_by_their_tick(self):
        """The property the whole drill-down rests on: a tick accounts for its actions."""
        tree, recorder = self.build(make_action("slow", ticks=5, sleep=0.05))
        tree.tick()
        tree.tick()
        recorder.close()
        by_tick = {}
        for row in self.actions():
            if row["phase"] != tick_recorder.PHASE_UPDATE:
                continue
            by_tick.setdefault(row["tick"], 0.0)
            by_tick[row["tick"]] += float(row["duration_s"])
        self.assertTrue(by_tick)
        for tick_row in self.ticks():
            spent = by_tick.get(tick_row["tick"])
            if spent is None:
                continue
            self.assertLessEqual(spent, float(tick_row["duration_s"]) + 1e-9)

    def test_a_slow_action_shows_up_in_both_files(self):
        """Time INSIDE a tick: the tick is long and an action row accounts for it."""
        tree, recorder = self.build(make_action("slow", ticks=5, sleep=0.05), period=0.01)
        tree.tick()
        recorder.close()
        tick_row = self.ticks()[0]
        self.assertGreater(float(tick_row["duration_s"]), 0.04)
        update = [row for row in self.actions() if row["phase"] == tick_recorder.PHASE_UPDATE][0]
        self.assertGreater(float(update["duration_s"]), 0.04)
        self.assertEqual(update["behavior_name"], "slow")

    def test_a_gap_between_ticks_is_not_attributed_to_any_action(self):
        """Time BETWEEN ticks: the interval is long, the tick is not, nothing accounts for it."""
        tree, recorder = self.build(make_action("quick", ticks=5), period=0.01)
        tree.tick()
        time.sleep(0.08)
        tree.tick()
        recorder.close()
        rows = self.ticks()
        self.assertGreater(float(rows[1]["interval_s"]), 0.07)
        self.assertLess(float(rows[0]["duration_s"]), 0.05)
        spent = sum(float(row["duration_s"]) for row in self.actions()
                    if row["phase"] == tick_recorder.PHASE_UPDATE)
        self.assertLess(spent, 0.05, "the gap belongs to no action")

    def test_actions_inserted_at_runtime_are_picked_up(self):
        root = py_trees.composites.Parallel(
            "par", py_trees.common.ParallelPolicy.SuccessOnAll(), [make_action("first", ticks=9)])
        tree, recorder = self.build(root)
        tree.tick()
        tree.insert_subtree(make_action("late", ticks=9), root.id, 1)
        tree.tick()
        recorder.close()
        self.assertIn("late", {row["behavior_name"] for row in self.actions()})

    def test_an_existing_tree_update_handler_is_chained(self):
        """A single callable slot, so it must be extended rather than taken over."""
        called = []
        tree = py_trees.trees.BehaviourTree(
            py_trees.composites.Parallel("par", py_trees.common.ParallelPolicy.SuccessOnAll(),
                                         [make_action("first", ticks=9)]))
        tree.tree_update_handler = lambda: called.append(True)
        recorder = TickRecorder(self.dir, 0.1, tick_recorder.DRIVER_WALL_LOOP)
        recorder.install_on_tree(tree)
        recorder.watch_tree_updates(tree)
        tree.insert_subtree(make_action("late", ticks=9), tree.root.id, 1)
        recorder.close()
        self.assertEqual(called, [True])

    def test_installing_twice_does_not_double_wrap(self):
        root = make_action("a", ticks=5)
        tree, recorder = self.build(root)
        recorder.install_on_tree(tree)
        recorder.install_on_tree(tree)
        tree.tick()
        recorder.close()
        updates = [row for row in self.actions() if row["phase"] == tick_recorder.PHASE_UPDATE]
        self.assertEqual(len(updates), 1)


class TestDisabledPathUntouched(unittest.TestCase):
    """The default is off, and off must cost nothing at all -- not merely little.

    These are structural assertions rather than timing comparisons, so the
    guarantee is pinned deterministically instead of flakily.
    """
    # pylint: disable=missing-function-docstring

    def test_an_action_is_not_wrapped_unless_a_recorder_installs_it(self):
        action = make_action("a")
        for method in ("setup", "initialise", "update"):
            self.assertNotIn(method, vars(action),
                             f"{method} was shadowed on the instance without --tick-log")
            self.assertFalse(getattr(getattr(action, method),
                                     "scenario_execution_timing_wrapper", False))

    def test_a_ticked_tree_gains_no_handlers_of_its_own(self):
        tree = py_trees.trees.BehaviourTree(make_action("a", ticks=5))
        self.assertEqual(tree.pre_tick_handlers, [])
        self.assertEqual(tree.post_tick_handlers, [])
        self.assertIsNone(tree.tree_update_handler)
        tree.tick()
        self.assertEqual(tree.pre_tick_handlers, [])
        self.assertEqual(tree.post_tick_handlers, [])
        self.assertIsNone(tree.tree_update_handler)
        self.assertNotIn("update", vars(tree.root))


if __name__ == '__main__':
    unittest.main()
