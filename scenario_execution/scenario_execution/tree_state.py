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

Which action is running, how long it has been in it, and what already finished --
``behaviors.jsonl`` holds all of it, and nothing could read it back. Useful for watching a run
progress, for checking afterwards that it did the steps it was meant to, and for looking at one
that is not doing what you expected; a scenario between status changes prints nothing at all, so
the log is the only thing that knows.

**It reports, it does not judge.** An action that has been running for minutes may be exactly
right: scenarios wait -- for a topic, for a duration, for a robot to arrive. Nothing here calls
that wrong, and a caller that wants a verdict has to bring its own expectation of what this
scenario should be doing.

The sibling of :mod:`scenario_execution.introspection` and deliberately not part of it:
that module answers *static* questions ("what does this environment offer", "what does
this file reference"), which are true before anything runs. This one answers a *runtime*
question about one particular execution, and mixing the two would make a module that is
sometimes about a file and sometimes about a process.

**Why the whole file has to be read.** The log is a metadata line, then a snapshot of every
node at timestamp 0, then **one record per behaviour whose status changed** -- see
:mod:`scenario_execution.utils.bt_logger`. So the current tree is the snapshot plus a fold
over every later record; the last line alone says only what changed last, which may have been
a long time ago. That cost is why this is a question a caller asks when it wants the answer,
rather than something cheap enough to poll.

Reads nothing but the file it is given, and imports nothing but the standard library: no
py_trees, no middleware, no simulator. A run that is misbehaving is when its environment is
least trustworthy, and that is one of the times someone reads this -- so needing the runtime to
import would make it unavailable in the case it is most wanted.

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


def _node_view(node, now=None):
    """One node, as a caller wants to read it rather than as the record stores it.

    Deliberately not the record: ``behavior_id``/``parent_id`` are UUIDs that exist to link
    records, and a reader handed thirty of them pays for thirty joins it should not have to do --
    the tree below carries the structure instead. ``is_active`` and ``child_index`` go for the
    same reason: the first nearly restates ``status``, and the second only means anything as the
    order children are already in.

    *now* is the caller's clock, or ``None``. ``for_s`` appears only when it was given *and* the
    node is running: on a finished node the same subtraction means "how long since it ended",
    which is a different quantity wearing the same name. Not a verdict either way -- an action may
    sit in one state for a long time because that is what it was asked to do.
    """
    status = node.get("status", _INVALID)
    since = node.get("timestamp")
    view = {"name": node.get("behavior_name"), "type": node.get("type"), "status": status}
    if since is not None:
        view["since"] = since
        if now is not None and status == _RUNNING:
            view["for_s"] = round(now - since, 1)
    if node.get("feedback_message"):
        view["feedback"] = node["feedback_message"]
    where = [node.get("osc_file"), node.get("osc_line")]
    if where[0]:
        # Where the action is written, so a caller can go straight to the line rather than
        # searching a name that may appear more than once.
        view["osc"] = f"{where[0]}:{where[1]}" if where[1] else where[0]
    return view


def _build_tree(nodes, now=None):
    """The nodes as a nested tree, children in declaration order.

    Reconstructed here because it is reconstructible here: every record carries its parent, and a
    caller doing that join itself would be re-deriving structure this module already has in hand.
    Children sort by ``child_index``, which is the only thing that field is for.

    Cycles and orphans cannot come from a real log, but a truncated or hand-edited one could carry
    a parent that is not present; such a node is attached at the top rather than dropped, because
    losing a node silently is worse than showing one whose place is unclear.
    """
    children = {}
    for node in nodes.values():
        children.setdefault(node.get("parent_id"), []).append(node)
    known = set(nodes)
    roots = [n for n in nodes.values()
             if n.get("parent_id") is None or n.get("parent_id") not in known]

    def build(node, seen):
        view = _node_view(node, now)
        node_id = node.get("behavior_id")
        kids = sorted(children.get(node_id, []), key=lambda n: n.get("child_index") or 0)
        kids = [k for k in kids if k.get("behavior_id") not in seen]
        if kids:
            view["children"] = [build(k, seen | {node_id}) for k in kids]
        return view

    built = [build(r, {r.get("behavior_id")}) for r in roots]
    return built[0] if len(built) == 1 else built


def _path_to(nodes, node):
    """``root > sequence > drive_to`` for *node*, so its place is readable without walking."""
    names, seen = [], set()
    while node is not None and node.get("behavior_id") not in seen:
        seen.add(node.get("behavior_id"))
        names.append(node.get("behavior_name") or "?")
        node = nodes.get(node.get("parent_id"))
    return " > ".join(reversed(names))


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


def tree_state(target, include_tree=True, now=None):
    """Where the scenario in *target* has got to, as plain data.

    Args:
        target: The log file, or a directory holding one (see :func:`find_log`).
        include_tree: With ``False``, report only the running action and the counts -- the whole
            tree is usually what a reader wants, but it is also most of the reply, so a caller
            polling "is it still on the same action" can decline it.
        now: The caller's current time **in this log's clock** (see ``clock`` in the reply). Given,
            every running node gains ``for_s``. Omitted, none does: the log records when things
            changed and has no way to know how long ago that was, and inventing a number from its
            own newest stamp would report every running action as having just started.

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
    # The newest stamp is when something last CHANGED, which is all the log knows -- and is not
    # "now". Using it as now was worse than useless: the running node is itself the newest record,
    # so its duration came out as 0.0 every time. The log cannot know the current time; only a
    # caller holding the same clock can, which is why *now* is an argument.
    stamps = [n["timestamp"] for n in nodes.values() if n.get("timestamp") is not None]
    last_change = max(stamps) if stamps else None
    running = _running_leaf(nodes)
    out = {
        "found": True,
        "log": path,
        "scenario": meta.get("scenario"),
        "started_at": meta.get("started_at"),
        #: Which clock every stamp here is in -- ``Clock`` is the scenario's (sim) time,
        #: ``monotonic`` is wall. Reported because "31.4" means different things in each, and
        #: because a caller supplying *now* has to supply it in this one.
        "clock": meta.get("clock"),
        #: When anything last changed status. A caller with the same clock subtracts to get "how
        #: long has nothing happened", which is the question the log can support; it cannot supply
        #: the other half itself.
        "last_change": last_change,
        "running": None,
        "counts": counts,
    }
    if running is not None:
        out["running"] = {**_node_view(running, now), "path": _path_to(nodes, running)}
    if include_tree:
        out["tree"] = _build_tree(nodes, now)
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
    parser.add_argument("--now", type=float, default=None, metavar="T",
                        help="your current time in this log's clock; adds how long each running "
                             "node has been running. Without it there is no such number to give.")
    args = parser.parse_args(argv)
    result = tree_state(args.target, include_tree=not args.no_tree, now=args.now)
    print(json.dumps(result, indent=2))
    return 0 if result.get("found") else 1


if __name__ == "__main__":
    sys.exit(main())
