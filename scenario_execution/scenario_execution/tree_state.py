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

"""Where a scenario has got to, read from the log its own behaviour tree writes.

A running scenario that has stopped making progress says almost nothing on stdout -- the
tree ticks, nothing changes status, and no line is printed. But ``behaviors.jsonl`` still
holds exactly where it is: which action is running, since when, and everything that
already finished. This reads that back.

The sibling of :mod:`scenario_execution.introspection` and deliberately not part of it:
that module answers *static* questions ("what does this environment offer", "what does
this file reference"), which are true before anything runs. This one answers a *runtime*
question about one particular execution, and mixing the two would make a module that is
sometimes about a file and sometimes about a process.

**Why the whole file has to be read.** The log is a metadata line, then a snapshot of every
node at timestamp 0, then **one record per behaviour whose status changed** -- see
:mod:`scenario_execution.utils.bt_logger`. So the current tree is the snapshot plus a fold
over every later record; the last line alone says only what changed last, which for a
stalled scenario is something that stopped mattering minutes ago. That cost is why this is
a separate question a caller asks when it wants the answer, rather than something cheap
enough to poll.

Reads nothing but the file it is given, and imports nothing but the standard library: no
py_trees, no middleware, no simulator. A stalled run is exactly when the environment is
least trustworthy, so a diagnostic that needed the runtime to load would be unavailable
when it mattered.

Runnable as a module so a caller outside the container can parse its JSON::

    python -m scenario_execution.tree_state <run-dir-or-file>
"""

import argparse
import glob
import json
import os
import sys

#: What :mod:`scenario_execution.utils.bt_logger` names its file. Duplicated rather than
#: imported so this module keeps its "standard library only" promise -- importing the logger
#: would pull in py_trees. ``test_tree_state`` asserts the two agree.
DEFAULT_FILENAME = "behaviors.jsonl"

#: The ``format`` value the first line carries, identifying it as this log rather than some
#: other JSONL that happens to share a name.
FORMAT_NAME = "behavior_tree_log"

#: py_trees statuses, in the order a reader wants them summarised.
_RUNNING = "RUNNING"
_INVALID = "INVALID"


def _read_records(path):
    """Every JSON object in the log, plus a count of lines that were not one.

    A truncated final line is normal: the file is appended to while a scenario runs, so a
    reader can arrive mid-write. It is counted and skipped rather than raised, because one
    unreadable line does not make the rest of the tree unknown -- and because failing here
    would mean the answer is only available once the run is over, which is the opposite of
    what this is for.
    """
    records, unreadable = [], 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError:
                unreadable += 1
    return records, unreadable


def _fold(records):
    """Collapse the record stream into the current state of every node, in first-seen order.

    Later records replace earlier ones for the same ``behavior_id``: that is what makes this
    a fold rather than a filter. Order is the snapshot's, so a caller reading the result sees
    the tree in the shape it was declared rather than in the order things happened to change.
    """
    nodes, meta = {}, {}
    for record in records:
        if record.get("format") == FORMAT_NAME:
            meta = record
            continue
        node_id = record.get("behavior_id")
        if node_id is None:
            continue
        nodes[node_id] = {**nodes.get(node_id, {}), **record}
    return meta, nodes


def _running_leaf(nodes):
    """The deepest node that is currently RUNNING, or ``None``.

    Taken from ``tip_id`` rather than by scanning for RUNNING nodes, because scanning finds
    the wrong thing: a Sequence is RUNNING for as long as any child is, so a scan returns a
    branch when what a caller asked was "what is actually executing". The tip is py_trees'
    own answer to that, recorded per node, so the root's tip is the tree's.
    """
    running = [n for n in nodes.values() if n.get("status") == _RUNNING]
    if not running:
        return None
    for node in running:
        # A composite's tip is its child; only the node actually executing is its own tip.
        if node.get("tip_id") and node["tip_id"] == node.get("behavior_id"):
            return node
    # No node claimed itself: an older log without tips, or a composite with no tip recorded.
    # The last RUNNING record is then the best available answer, and saying which is why the
    # caller gets the whole tree alongside it.
    return running[-1]


def _node_view(node):
    """One node, as a caller wants to read it rather than as the record stores it."""
    view = {
        "name": node.get("behavior_name"),
        "type": node.get("type"),
        "status": node.get("status", _INVALID),
        "since": node.get("timestamp"),
        "active": bool(node.get("is_active")),
    }
    for key, source in (("feedback", "feedback_message"), ("id", "behavior_id"),
                        ("parent", "parent_id"), ("child_index", "child_index")):
        if node.get(source) not in (None, ""):
            view[key] = node[source]
    where = [node.get("osc_file"), node.get("osc_line")]
    if where[0]:
        # Where the action is written, so a caller can go straight to the line rather than
        # searching a name that may appear more than once.
        view["osc"] = f"{where[0]}:{where[1]}" if where[1] else where[0]
    return view


def find_log(target):
    """The behaviour-tree log for *target*, which may be the file or a directory holding it.

    Searches *target*, then one and two levels below, newest first at the depth that has one.
    A caller often knows an output root rather than the run inside it -- the run currently
    being written is the newest -- and being able to name the root is the difference between
    this being usable from outside a single run and not.
    """
    if os.path.isfile(target):
        return target
    for pattern in (DEFAULT_FILENAME, f"*/{DEFAULT_FILENAME}", f"*/*/{DEFAULT_FILENAME}"):
        found = glob.glob(os.path.join(target, pattern))
        if found:
            return max(found, key=os.path.getmtime)
    return None


def tree_state(target, include_tree=True):
    """Where the scenario in *target* has got to, as plain data.

    Args:
        target: The log file, or a directory holding one (see :func:`find_log`).
        include_tree: With ``False``, report only the running action and the counts. The whole
            tree is the useful answer for a human looking at a wedge, but it is also the bulk
            of the reply, so a caller polling for "is it still on the same action" can decline
            it.

    Returns:
        ``{"found": False, "error": ...}`` when there is no readable log -- an error rather
        than an empty tree, because "the scenario has no nodes" and "nobody could read the
        log" are different answers and must not render alike. Otherwise ``{found, log,
        scenario, started_at, running, counts, nodes?, unreadable_lines?}``, where ``running``
        is the currently executing action or ``None`` for a scenario that has finished or not
        yet begun.
    """
    path = find_log(target)
    if path is None:
        return {"found": False,
                "error": f"no {DEFAULT_FILENAME} in or below {target!r}. A scenario writes one "
                         f"only when run with --bt-log, so this run may have opted out."}
    try:
        records, unreadable = _read_records(path)
    except OSError as err:
        return {"found": False, "error": f"could not read {path}: {err}"}
    meta, nodes = _fold(records)
    if not nodes:
        return {"found": False,
                "error": f"{path} holds no behaviour records yet: the scenario has been "
                         f"launched but has not ticked."}
    counts = {}
    for node in nodes.values():
        status = node.get("status", _INVALID)
        counts[status] = counts.get(status, 0) + 1
    running = _running_leaf(nodes)
    out = {
        "found": True,
        "log": path,
        "scenario": meta.get("scenario"),
        "started_at": meta.get("started_at"),
        "running": _node_view(running) if running else None,
        "counts": counts,
    }
    if include_tree:
        out["nodes"] = [_node_view(n) for n in nodes.values()]
    if unreadable:
        # Never silent: a caller comparing two reads needs to know one of them was partial.
        out["unreadable_lines"] = unreadable
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m scenario_execution.tree_state",
        description="Where a scenario has got to, from the log its behaviour tree writes.")
    parser.add_argument("target", nargs="?", default=".",
                        help=f"a {DEFAULT_FILENAME}, or a directory holding one")
    parser.add_argument("--no-tree", action="store_true",
                        help="report only the running action and the status counts")
    args = parser.parse_args(argv)
    result = tree_state(args.target, include_tree=not args.no_tree)
    print(json.dumps(result, indent=2))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    sys.exit(main())
