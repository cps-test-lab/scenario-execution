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

"""Reading back where a scenario has got to, from the log its behaviour tree wrote."""
import ast
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from scenario_execution import tree_state
from scenario_execution.utils import bt_logger


def _write(directory, lines, name=None):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name or tree_state.DEFAULT_FILENAME)
    with open(path, "w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")
    return path


def _meta(**over):
    base = {"format": tree_state.FORMAT_NAME, "version": 1, "scenario": "drive",
            "started_at": "2026-08-20T12:00:00+00:00"}
    base.update(over)
    return base


def _node(node_id, name, status, *, tip=None, parent=None, kind="BEHAVIOUR",  # pylint: disable=too-many-arguments
          timestamp=0.0, feedback="", line=12):
    """One record, shaped as a real run writes it.

    ``tip_id`` defaults to **None**, which is what a leaf actually records -- the tip points
    *downwards*, so only composites carry one. An earlier version of this helper defaulted it to
    the node's own id, and that fiction hid a bug that reported the root as the running action on
    every real run.
    """
    return {"timestamp": timestamp, "behavior_id": node_id, "behavior_name": name,
            "type": kind, "status": status, "tip_id": tip,
            "parent_id": parent, "is_active": status == "RUNNING",
            "feedback_message": feedback, "child_index": 0,
            "osc_file": "drive.osc", "osc_line": line}


class TestTreeState(unittest.TestCase):
    """Reading a behaviour-tree log back as state."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.dir.cleanup)

    def test_the_filename_matches_the_writer(self):
        """This module duplicates the name so it need not import py_trees. Duplication is only
        safe while something notices it drifting, and this is that something."""
        self.assertEqual(tree_state.DEFAULT_FILENAME, bt_logger.DEFAULT_FILENAME)
        self.assertEqual(tree_state.FORMAT_NAME, bt_logger.FORMAT_NAME)

    def test_the_current_state_is_the_fold_not_the_last_line(self):
        """The log records one line per status change, so the last line says only what changed
        last -- which for a stalled scenario stopped mattering minutes ago. Every node's current
        status has to come from folding the stream."""
        _write(self.dir.name, [
            _meta(),
            _node("a", "drive_to", "INVALID"),
            _node("b", "wait", "INVALID"),
            _node("a", "drive_to", "SUCCESS", timestamp=5.0),
            _node("b", "wait", "RUNNING", timestamp=5.0),
        ])
        state = tree_state.tree_state(self.dir.name)
        self.assertTrue(state["found"])
        self.assertEqual(state["counts"], {"SUCCESS": 1, "RUNNING": 1})
        by_name = {n["name"]: n for n in state["tree"]}
        self.assertEqual(by_name["drive_to"]["status"], "SUCCESS")
        self.assertEqual(by_name["wait"]["status"], "RUNNING")

    def test_the_running_action_is_the_tip_not_the_branch(self):
        """A Sequence is RUNNING for as long as any child is, so scanning for RUNNING nodes
        returns a branch when the caller asked what is *executing*.

        The tip is py_trees' own answer and it points DOWNWARDS: the root names the deepest node
        being ticked, and a leaf names nothing. So it is followed from the root -- which is the bug
        this pins. Looking for a node that was its own tip matched no real leaf, fell through to
        "the last RUNNING record", and reported the root on every live run."""
        _write(self.dir.name, [
            _meta(),
            _node("seq", "sequence", "RUNNING", tip="leaf", kind="SEQUENCE"),
            _node("leaf", "drive_to", "RUNNING", parent="seq", timestamp=31.4,
                  feedback="driving", line=24),
        ])
        state = tree_state.tree_state(self.dir.name)
        self.assertEqual(state["running"]["name"], "drive_to")
        self.assertEqual(state["running"]["since"], 31.4)
        self.assertEqual(state["running"]["feedback"], "driving")
        # Where it is written, so a reader goes to the line instead of grepping a name -- which
        # matters because two actions of the same kind share a name and only differ by line.
        self.assertEqual(state["running"]["osc"], "drive.osc:24")

    def test_the_deepest_running_node_is_used_when_no_tip_was_recorded(self):
        """An older log, or a tip naming a node the log does not hold. The deepest RUNNING node --
        the one that is not another's parent -- is still a better answer than a branch."""
        _write(self.dir.name, [
            _meta(),
            _node("seq", "sequence", "RUNNING", kind="SEQUENCE"),
            _node("leaf", "drive_to", "RUNNING", parent="seq", timestamp=31.4),
        ])
        self.assertEqual(tree_state.tree_state(self.dir.name)["running"]["name"], "drive_to")

    def test_an_elapsed_time_log_gets_its_duration_derived(self):
        """A ``monotonic`` log's stamps are elapsed from the run's start, and ``started_at`` says
        when that was -- so the duration comes from wall time and needs nothing from the caller."""
        started = datetime.now(timezone.utc) - timedelta(seconds=30)
        _write(self.dir.name, [
            _meta(clock="monotonic", started_at=started.isoformat(timespec="seconds")),
            _node("a", "wait", "RUNNING", timestamp=2.0),
        ])
        state = tree_state.tree_state(self.dir.name)
        self.assertAlmostEqual(state["now"], 30.0, delta=2.0)
        self.assertAlmostEqual(state["running"]["for_s"], 28.0, delta=2.0)

    def test_a_callers_monotonic_reading_is_refused_rather_than_subtracted(self):
        """That clock counts from an arbitrary per-process origin, so a reader's value and the
        log's are unrelated numbers. Subtracting them reported 254472 s on a run three seconds
        old -- a number that looked like a duration and was not one."""
        _write(self.dir.name, [
            _meta(clock="monotonic", started_at="2026-08-20T12:00:00+00:00"),
            _node("a", "wait", "RUNNING", timestamp=2.0),
        ])
        state = tree_state.tree_state(self.dir.name, now=254474.0)
        # Derived from started_at instead, which is large but *true*; never the caller's number.
        self.assertNotEqual(state["now"], 254474.0)

    def test_a_finished_scenario_has_no_running_action(self):
        """``None`` rather than a guess: a scenario that ended is not still in its last action."""
        _write(self.dir.name, [_meta(), _node("a", "drive_to", "SUCCESS", timestamp=9.0)])
        self.assertIsNone(tree_state.tree_state(self.dir.name)["running"])

    def test_no_duration_is_invented_for_a_sim_time_log_without_a_clock(self):
        """Sim time cannot be derived from wall time -- a simulator runs at whatever rate it runs
        at -- so with no caller clock there is no duration, and none is offered. Deriving one from
        the log's own newest stamp reported every running action as having just started, because
        the running node *is* the newest record."""
        _write(self.dir.name, [
            _meta(clock="Clock"),
            _node("a", "drive_to", "RUNNING", timestamp=31.4),
            _node("b", "log", "SUCCESS", timestamp=0.2),
        ])
        state = tree_state.tree_state(self.dir.name)
        self.assertEqual(state["last_change"], 31.4)
        self.assertIsNone(state["now"])
        self.assertNotIn("for_s", state["running"])

    def test_a_duration_is_reported_only_while_a_node_is_running(self):
        """With the caller's clock there is a real answer. On a finished node the same subtraction
        means "how long since it ended", a different quantity wearing the same name -- and it is
        not a verdict either way: a scenario waits on purpose."""
        _write(self.dir.name, [
            _meta(clock="Clock"),
            _node("a", "drive_to", "RUNNING", timestamp=31.4),
            _node("b", "log", "SUCCESS", timestamp=0.2),
        ])
        state = tree_state.tree_state(self.dir.name, now=333.4)
        by_name = {n["name"]: n for n in state["tree"]}
        self.assertEqual(by_name["drive_to"]["for_s"], 302.0)
        self.assertNotIn("for_s", by_name["log"])

    def test_the_tree_is_nested_so_structure_is_read_not_reassembled(self):
        """A flat list keyed by uuid makes every reader redo a join this module can do once -- and
        pays for it in ids nobody wants to look at."""
        _write(self.dir.name, [
            _meta(),
            _node("root", "root", "RUNNING", tip="leaf", kind="SEQUENCE"),
            _node("leaf", "drive_to", "RUNNING", tip="leaf", parent="root", timestamp=31.4),
        ])
        state = tree_state.tree_state(self.dir.name)
        self.assertEqual(state["tree"]["name"], "root")
        self.assertEqual([c["name"] for c in state["tree"]["children"]], ["drive_to"])
        self.assertNotIn("id", state["tree"])          # uuids are the record's, not a reader's
        self.assertEqual(state["running"]["path"], "root > drive_to")

    def test_the_clock_is_named_because_the_numbers_depend_on_it(self):
        """"31.4" is sim seconds or wall seconds depending on how the scenario was run, and a
        reader comparing it with anything has to know which."""
        _write(self.dir.name, [_meta(clock="Clock"), _node("a", "x", "RUNNING")])
        self.assertEqual(tree_state.tree_state(self.dir.name)["clock"], "Clock")

    def test_a_truncated_final_line_is_counted_not_fatal(self):
        """The file is appended to while the scenario runs, so a reader can arrive mid-write.
        Raising would make this answerable only once the run is over -- the opposite of the
        point -- but a silent skip would hide that a read was partial."""
        path = _write(self.dir.name, [_meta(), _node("a", "drive_to", "RUNNING")])
        with open(path, "a", encoding="utf-8") as handle:
            handle.write('{"behavior_id": "b", "behavior_na')
        state = tree_state.tree_state(self.dir.name)
        self.assertEqual(state["running"]["name"], "drive_to")
        self.assertEqual(state["unreadable_lines"], 1)

    def test_a_missing_log_is_an_error_not_an_empty_tree(self):
        """"The scenario has no nodes" and "nobody could read the log" are different answers.
        Rendering them alike would report a run nobody could see as one doing nothing."""
        state = tree_state.tree_state(self.dir.name)
        self.assertFalse(state["found"])
        self.assertIn("bt-log", state["error"])

    def test_a_log_with_no_ticks_yet_says_so(self):
        """Launched but not ticking is its own state, and a caller waiting for the first action
        needs to tell it apart from a scenario that has finished."""
        _write(self.dir.name, [_meta()])
        state = tree_state.tree_state(self.dir.name)
        self.assertFalse(state["found"])
        self.assertIn("has not ticked", state["error"])

    def test_the_run_is_found_below_the_directory_given(self):
        """A caller often knows an output root rather than the run inside it. The newest log is
        the run still being written."""
        old = os.path.join(self.dir.name, "cfg", "0")
        new = os.path.join(self.dir.name, "cfg", "1")
        _write(old, [_meta(scenario="old"), _node("a", "a", "SUCCESS")])
        _write(new, [_meta(scenario="new"), _node("a", "b", "RUNNING")])
        os.utime(os.path.join(old, tree_state.DEFAULT_FILENAME), (1, 1))
        state = tree_state.tree_state(self.dir.name)
        self.assertEqual(state["scenario"], "new")

    def test_no_tree_keeps_the_answer_without_the_bulk(self):
        """The whole tree is what a human wants on a wedge, but it is also most of the reply, so
        a caller polling "is it still on the same action" can decline it."""
        _write(self.dir.name, [_meta(), _node("a", "drive_to", "RUNNING")])
        state = tree_state.tree_state(self.dir.name, include_tree=False)
        self.assertNotIn("tree", state)
        self.assertEqual(state["running"]["name"], "drive_to")
        self.assertEqual(state["counts"], {"RUNNING": 1})

    def test_it_imports_nothing_but_the_standard_library(self):
        """A stalled run is when the environment is least trustworthy, so a diagnostic that
        needed py_trees or a middleware to load would be unavailable exactly when it mattered."""
        source = os.path.join(os.path.dirname(tree_state.__file__), "tree_state.py")
        with open(source, "r", encoding="utf-8") as handle:
            parsed = ast.parse(handle.read())
        imported = set()
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.col_offset == 0:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported, {"argparse", "datetime", "glob", "json", "os", "sys"})
