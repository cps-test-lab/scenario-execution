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
Test the behaviour tree status log (--bt-log)
"""
import json
import os
import tempfile
import unittest

import py_trees

from scenario_execution.simulation import Clock
from scenario_execution.utils.bt_logger import BehaviourTreeJsonlLogger, build_meta


class FakeClock(Clock):
    """A clock the test advances by hand, standing in for a SimulationClock."""

    def __init__(self):
        self.value = 0.0

    def now(self) -> float:
        return self.value


class Countdown(py_trees.behaviour.Behaviour):
    """RUNNING for *ticks* ticks, then SUCCESS."""

    def __init__(self, name, ticks):
        super().__init__(name)
        self.remaining = ticks

    def update(self):
        self.remaining -= 1
        self.feedback_message = f"{self.remaining} left"
        if self.remaining <= 0:
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.RUNNING


class TestBtLogger(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.path = os.path.join(self.tmp.name, "behaviors.jsonl")
        self.clock = FakeClock()

    def tearDown(self):
        self.tmp.cleanup()

    def build_logger(self, tree, clock=None):
        logger = BehaviourTreeJsonlLogger(
            self.path, build_meta("test", "test.osc", 0.1, clock), clock)
        tree.add_visitor(logger.snapshot_visitor)
        logger.write_initial_snapshot(tree)
        tree.add_post_tick_handler(logger)
        return logger

    def read(self):
        with open(self.path, encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle]
        return records[0], records[1:]

    @staticmethod
    def simple_tree():
        """root(Sequence) -> [slow(2 ticks), inner(Sequence) -> [quick, never]]"""
        root = py_trees.composites.Sequence(name="root", memory=True)
        inner = py_trees.composites.Sequence(name="inner", memory=True)
        inner.add_children([py_trees.behaviours.Success(name="quick"),
                            py_trees.behaviours.Success(name="never")])
        root.add_children([Countdown("slow", 2), inner])
        return py_trees.trees.BehaviourTree(root)

    def test_meta_record(self):
        tree = self.simple_tree()
        self.build_logger(tree, self.clock).close()
        meta, _ = self.read()
        self.assertEqual(meta["format"], "behavior_tree_log")
        self.assertEqual(meta["scenario"], "test")
        self.assertEqual(meta["clock"], "FakeClock")
        self.assertIsNotNone(meta["py_trees"])

    def test_initial_snapshot_covers_every_node(self):
        tree = self.simple_tree()
        logger = self.build_logger(tree, self.clock)
        logger.close()
        _, events = self.read()
        self.assertTrue(all(e["timestamp"] == 0.0 for e in events))
        self.assertTrue(all(e["status"] == "INVALID" for e in events))
        self.assertEqual({e["behavior_name"] for e in events},
                         {"root", "slow", "inner", "quick", "never"})

    def test_never_ticked_node_is_recorded(self):
        # 'never' is only reached after 'quick', which only runs once 'slow' succeeds.
        # A pure delta stream would omit a branch like this entirely.
        tree = self.simple_tree()
        logger = self.build_logger(tree, self.clock)
        tree.tick()
        logger.close()
        _, events = self.read()
        self.assertIn("never", {e["behavior_name"] for e in events})

    def test_record_per_status_change_only(self):
        tree = self.simple_tree()
        logger = self.build_logger(tree, self.clock)
        _, initial = self.read()
        for _ in range(3):
            self.clock.value += 0.5
            tree.tick()
        logger.close()
        _, events = self.read()
        changes = events[len(initial):]
        self.assertTrue(changes)
        for behavior_id in {e["behavior_id"] for e in changes}:
            statuses = [e["status"] for e in changes if e["behavior_id"] == behavior_id]
            self.assertEqual(statuses, list(dict.fromkeys(statuses)),
                             "a status was recorded twice in a row")

    def test_timestamp_from_clock(self):
        tree = self.simple_tree()
        logger = self.build_logger(tree, self.clock)
        self.clock.value = 12.5
        tree.tick()
        logger.close()
        _, events = self.read()
        self.assertEqual({e["timestamp"] for e in events if e["timestamp"] != 0.0}, {12.5})

    def test_timestamp_without_clock_starts_at_zero(self):
        tree = self.simple_tree()
        logger = self.build_logger(tree, clock=None)
        tree.tick()
        logger.close()
        meta, events = self.read()
        self.assertEqual(meta["clock"], "monotonic")
        self.assertTrue(all(0.0 <= e["timestamp"] < 5.0 for e in events))

    def test_child_index_orders_siblings(self):
        tree = self.simple_tree()
        self.build_logger(tree, self.clock).close()
        _, events = self.read()
        by_name = {e["behavior_name"]: e for e in events}
        self.assertIsNone(by_name["root"]["parent_id"])
        self.assertIsNone(by_name["root"]["child_index"])
        self.assertEqual(by_name["slow"]["child_index"], 0)
        self.assertEqual(by_name["inner"]["child_index"], 1)
        self.assertEqual(by_name["quick"]["child_index"], 0)
        self.assertEqual(by_name["never"]["child_index"], 1)

    def test_tree_is_reconstructable(self):
        tree = self.simple_tree()
        logger = self.build_logger(tree, self.clock)
        for _ in range(3):
            self.clock.value += 0.5
            tree.tick()
        logger.close()
        _, events = self.read()

        nodes = {}
        for event in events:
            nodes.setdefault(event["behavior_id"], event).update(event)
        children = {}
        for node in nodes.values():
            if node["parent_id"] is not None:
                self.assertIn(node["parent_id"], nodes, "dangling parent_id")
                children.setdefault(node["parent_id"], []).append(node)
        for siblings in children.values():
            siblings.sort(key=lambda n: n["child_index"])

        def names(node):
            return [n["behavior_name"] for n in children.get(node["behavior_id"], [])]

        root = next(n for n in nodes.values() if n["parent_id"] is None)
        self.assertEqual(root["behavior_name"], "root")
        self.assertEqual(names(root), ["slow", "inner"])
        inner = next(n for n in nodes.values() if n["behavior_name"] == "inner")
        self.assertEqual(names(inner), ["quick", "never"])

    def test_types_and_tip(self):
        tree = self.simple_tree()
        logger = self.build_logger(tree, self.clock)
        self.clock.value = 1.0
        tree.tick()
        logger.close()
        _, events = self.read()
        running = [e for e in events if e["timestamp"] == 1.0]
        root = next(e for e in running if e["behavior_name"] == "root")
        slow = next(e for e in running if e["behavior_name"] == "slow")
        self.assertEqual(root["type"], "SEQUENCE")
        self.assertEqual(slow["type"], "BEHAVIOUR")
        # The ancestor points at the leaf that determined its status; the leaf itself
        # has no tip, matching py_trees_ros.
        self.assertEqual(root["tip_id"], slow["behavior_id"])
        self.assertIsNone(slow["tip_id"])
        self.assertTrue(slow["is_active"])
        self.assertEqual(slow["feedback_message"], "1 left")

    def test_parallel_policy_in_additional_detail(self):
        root = py_trees.composites.Parallel(
            name="par", policy=py_trees.common.ParallelPolicy.SuccessOnAll())
        root.add_child(py_trees.behaviours.Running(name="forever"))
        tree = py_trees.trees.BehaviourTree(root)
        self.build_logger(tree, self.clock).close()
        _, events = self.read()
        par = next(e for e in events if e["behavior_name"] == "par")
        self.assertEqual(par["type"], "PARALLEL")
        self.assertIn("OnAll", par["additional_detail"])

    def test_osc_source_is_reported_when_stamped(self):
        tree = self.simple_tree()
        tree.root.osc_source = ("/scenarios/demo.osc", 12, 4)
        self.build_logger(tree, self.clock).close()
        _, events = self.read()
        root = next(e for e in events if e["behavior_name"] == "root")
        unstamped = next(e for e in events if e["behavior_name"] == "quick")
        self.assertEqual(
            (root["osc_file"], root["osc_line"], root["osc_column"]),
            ("/scenarios/demo.osc", 12, 4))
        # A behaviour with no source element is a legitimate absence, not an error.
        self.assertIsNone(unstamped["osc_file"])

    def test_runtime_insert_and_prune(self):
        root = py_trees.composites.Sequence(name="root", memory=True)
        root.add_child(py_trees.behaviours.Running(name="forever"))
        tree = py_trees.trees.BehaviourTree(root)
        logger = self.build_logger(tree, self.clock)
        tree.tick()

        self.clock.value = 1.0
        added = py_trees.behaviours.Running(name="added")
        tree.insert_subtree(added, root.id, 1)
        tree.tick()
        _, events = self.read()
        self.assertIn("added", {e["behavior_name"] for e in events})

        self.clock.value = 2.0
        tree.prune_subtree(added.id)
        tree.tick()
        logger.close()
        _, events = self.read()
        removed = [e for e in events if e.get("removed")]
        self.assertEqual([e["behavior_id"] for e in removed], [str(added.id)])

    def test_file_is_readable_after_an_abrupt_end(self):
        # Every record is flushed, so a run killed mid-scenario still yields a
        # parseable file -- exactly the run whose tree state is worth reading.
        tree = self.simple_tree()
        self.build_logger(tree, self.clock)
        tree.tick()
        meta, events = self.read()  # no close()
        self.assertEqual(meta["format"], "behavior_tree_log")
        self.assertTrue(events)


if __name__ == '__main__':
    unittest.main()
