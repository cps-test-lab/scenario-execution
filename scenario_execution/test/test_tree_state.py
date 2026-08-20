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
import json
import os
import tempfile
import unittest

from scenario_execution import tree_state


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


def _node(node_id, name, status, *, tip=None, parent=None, kind="BEHAVIOUR",
          timestamp=0.0, feedback=""):
    return {"timestamp": timestamp, "behavior_id": node_id, "behavior_name": name,
            "type": kind, "status": status, "tip_id": tip if tip is not None else node_id,
            "parent_id": parent, "is_active": status == "RUNNING",
            "feedback_message": feedback, "child_index": 0,
            "osc_file": "drive.osc", "osc_line": 12}


class TestTreeState(unittest.TestCase):

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.addCleanup(self.dir.cleanup)

    def test_the_filename_matches_the_writer(self):
        """This module duplicates the name so it need not import py_trees. Duplication is only
        safe while something notices it drifting, and this is that something."""
        from scenario_execution.utils import bt_logger
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
        by_name = {n["name"]: n for n in state["nodes"]}
        self.assertEqual(by_name["drive_to"]["status"], "SUCCESS")
        self.assertEqual(by_name["wait"]["status"], "RUNNING")

    def test_the_running_action_is_the_tip_not_the_branch(self):
        """A Sequence is RUNNING for as long as any child is, so scanning for RUNNING nodes
        returns a branch when the caller asked what is *executing*. The tip is py_trees' own
        answer, and a node that is its own tip is the one doing the work."""
        _write(self.dir.name, [
            _meta(),
            _node("seq", "sequence", "RUNNING", tip="leaf", kind="SEQUENCE"),
            _node("leaf", "drive_to", "RUNNING", tip="leaf", parent="seq",
                  timestamp=31.4, feedback="driving"),
        ])
        state = tree_state.tree_state(self.dir.name)
        self.assertEqual(state["running"]["name"], "drive_to")
        self.assertEqual(state["running"]["since"], 31.4)
        self.assertEqual(state["running"]["feedback"], "driving")
        # Where it is written, so a reader goes to the line instead of grepping a name.
        self.assertEqual(state["running"]["osc"], "drive.osc:12")

    def test_a_finished_scenario_has_no_running_action(self):
        """``None`` rather than a guess: a scenario that ended is not stuck in its last action."""
        _write(self.dir.name, [_meta(), _node("a", "drive_to", "SUCCESS", timestamp=9.0)])
        self.assertIsNone(tree_state.tree_state(self.dir.name)["running"])

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
        self.assertNotIn("nodes", state)
        self.assertEqual(state["running"]["name"], "drive_to")
        self.assertEqual(state["counts"], {"RUNNING": 1})

    def test_it_imports_nothing_but_the_standard_library(self):
        """A stalled run is when the environment is least trustworthy, so a diagnostic that
        needed py_trees or a middleware to load would be unavailable exactly when it mattered."""
        import ast
        source = os.path.join(os.path.dirname(tree_state.__file__), "tree_state.py")
        with open(source, "r", encoding="utf-8") as handle:
            parsed = ast.parse(handle.read())
        imported = set()
        for node in ast.walk(parsed):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.col_offset == 0:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported, {"argparse", "glob", "json", "os", "sys"})
