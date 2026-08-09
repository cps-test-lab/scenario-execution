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

"""Record behaviour-tree status over time to a self-contained JSONL file.

Middleware-independent: this module imports nothing but the standard library and
py_trees, so the same writer serves the plain and the ROS runner. The only thing
the ROS runner contributes is a :class:`~scenario_execution.simulation.Clock`
implementation reading ``/clock``.

File layout -- one JSON object per line:

* line 1 is the metadata record, identified by its ``format`` key: which scenario
  file was run (and its sha256), the tick period, which clock ``timestamp`` comes
  from, and the py_trees version.
* line 2..n+1 are a snapshot of every node in the tree at ``timestamp`` 0, all
  ``INVALID``. Without it, branches that never tick would be missing from the file
  entirely and the tree could not be fully reconstructed.
* afterwards, one record per behaviour whose **status** changed. ``feedback_message``
  is captured as it stands at that moment but does not itself trigger a record --
  some actions rewrite it every tick, which would turn this into a per-tick dump.

Records carry the full node description rather than referring back to the snapshot,
so every line stands on its own and reading the file is ``json.loads`` per line.
The field set follows ``py_trees_ros_interfaces/Behaviour`` -- see
:func:`_behaviour_record` for what is taken and what is deliberately left out.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone

import py_trees

FORMAT_NAME = "behavior_tree_log"
FORMAT_VERSION = 1

DEFAULT_FILENAME = "behaviors.jsonl"


def _behaviour_type(behaviour) -> str:
    """Node kind, mirroring py_trees_ros' ``behaviour_type_to_msg_constant``."""
    if isinstance(behaviour, py_trees.composites.Sequence):
        return "SEQUENCE"
    if isinstance(behaviour, py_trees.composites.Selector):
        return "SELECTOR"
    if isinstance(behaviour, py_trees.composites.Parallel):
        return "PARALLEL"
    if isinstance(behaviour, py_trees.decorators.Decorator):
        return "DECORATOR"
    if isinstance(behaviour, py_trees.behaviour.Behaviour):
        return "BEHAVIOUR"
    return "UNKNOWN_TYPE"


def _additional_detail(behaviour) -> str:
    """Policy information, mirroring py_trees_ros' ``additional_detail_to_str``."""
    if isinstance(behaviour, py_trees.composites.Parallel):
        try:
            policy = behaviour.policy.__class__.__name__.replace("Success", "")
        except AttributeError:
            return ""
        try:
            indices = [str(behaviour.children.index(child)) for child in behaviour.policy.children]
            policy += "({})".format(", ".join(sorted(indices)))
        except AttributeError:
            pass
        return policy
    return ""


def _child_index(behaviour):
    """Position among the parent's children -- ``parent_id`` alone yields an unordered set."""
    parent = behaviour.parent
    if parent is None:
        return None
    try:
        return parent.children.index(behaviour)
    except ValueError:
        return None


def _tip_id(behaviour):
    """The leaf that determined this subtree's status, or None for a leaf/invalid node.

    py_trees' ``tip()`` recurses through ``current_child`` (composites) and
    ``decorated`` (decorators), so on an ancestor this names the behaviour actually
    responsible for its status -- the one field here that cannot be recomputed from
    the others, since ``current_child`` is not logged.
    """
    tip = behaviour.tip()
    if tip is None or tip is behaviour:
        return None
    return str(tip.id)


def _behaviour_record(behaviour, timestamp: float, is_active: bool) -> dict:
    """One complete description of *behaviour* at *timestamp*.

    Fields follow ``py_trees_ros_interfaces/Behaviour``. Left out on purpose:
    ``child_ids`` and ``current_child_id`` (``child_index`` orders children and
    ``tip_id`` carries what ``current_child_id`` was needed for), ``blackbox_level``
    and ``blackboard_access`` (the blackboard is a separate concern).
    """
    source = getattr(behaviour, "osc_source", None)
    osc_file, osc_line, osc_column = source if source else (None, None, None)
    return {
        "timestamp": timestamp,
        "behavior_id": str(behaviour.id),
        "parent_id": str(behaviour.parent.id) if behaviour.parent else None,
        "child_index": _child_index(behaviour),
        "behavior_name": behaviour.name,
        "class_name": py_trees.utilities.get_fully_qualified_name(behaviour),
        "type": _behaviour_type(behaviour),
        "additional_detail": _additional_detail(behaviour),
        "status": behaviour.status.name,
        "feedback_message": behaviour.feedback_message,
        "is_active": is_active,
        "tip_id": _tip_id(behaviour),
        "osc_file": osc_file,
        "osc_line": osc_line,
        "osc_column": osc_column,
    }


def file_sha256(path: str):
    """Hash of *path*, or None if it cannot be read (a scenario given inline has no file)."""
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_meta(scenario_name: str, scenario_file: str, tick_period: float, clock) -> dict:
    """The file's first line: what produced it and what ``timestamp`` means."""
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "scenario": scenario_name,
        "scenario_file": scenario_file,
        "scenario_sha256": file_sha256(scenario_file),
        "tick_period": tick_period,
        "clock": type(clock).__name__ if clock is not None else "monotonic",
        "py_trees": py_trees.version.__version__,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


class BehaviourTreeJsonlLogger(object):
    """Post-tick handler writing behaviour status changes to a JSONL file.

    Usage::

        logger = BehaviourTreeJsonlLogger(path, meta, clock)
        behaviour_tree.add_visitor(logger.snapshot_visitor)
        logger.write_initial_snapshot(behaviour_tree)   # before the first tick
        behaviour_tree.add_post_tick_handler(logger)
        ...
        logger.close()

    Args:
        path: file to write; the parent directory must exist.
        meta: the metadata record, see :func:`build_meta`.
        clock: time source for ``timestamp``. ``None`` falls back to monotonic time
            measured from the initial snapshot, so ``timestamp`` counts from zero
            either way.
    """

    def __init__(self, path: str, meta: dict, clock=None):
        self._clock = clock
        self._monotonic_start = None
        # id -> last status written, the only state needed to emit deltas
        self._last_status = {}
        # Which behaviours the tick actually traversed. py_trees_ros fills its
        # `is_active` from the same source; a node can hold SUCCESS from an earlier
        # tick without being on the current path, so status alone cannot say this.
        self.snapshot_visitor = py_trees.visitors.SnapshotVisitor()
        self._file = open(path, "w", encoding="utf-8")  # pylint: disable=consider-using-with
        self._write(meta)

    @property
    def closed(self) -> bool:
        return self._file is None

    def now(self) -> float:
        """Seconds since the scenario started -- simulated time when a clock is given."""
        if self._clock is not None:
            return self._clock.now()
        if self._monotonic_start is None:
            self._monotonic_start = time.monotonic()
        return time.monotonic() - self._monotonic_start

    def write_initial_snapshot(self, behaviour_tree) -> None:
        """Record every node at ``timestamp`` 0, before the tree has ticked.

        Called separately from the post-tick handler because by the first post-tick
        the statuses have already changed -- and a node that never ticks would
        otherwise never appear.
        """
        if self._monotonic_start is None:
            self._monotonic_start = time.monotonic()
        for behaviour in behaviour_tree.root.iterate():
            self._write(_behaviour_record(behaviour, 0.0, is_active=False))
            self._last_status[behaviour.id] = behaviour.status

    def __call__(self, behaviour_tree) -> None:
        """Post-tick handler: a record per behaviour whose status changed."""
        if self._file is None:
            return
        timestamp = self.now()
        visited = self.snapshot_visitor.visited
        present = set()
        for behaviour in behaviour_tree.root.iterate():
            present.add(behaviour.id)
            # A node absent from _last_status was inserted at runtime (insert_subtree,
            # BaseActionSubtree); it gets a full record on first sight, same as any
            # status change would produce.
            if self._last_status.get(behaviour.id, None) == behaviour.status:
                continue
            self._last_status[behaviour.id] = behaviour.status
            self._write(_behaviour_record(behaviour, timestamp, is_active=behaviour.id in visited))
        for gone in [i for i in self._last_status if i not in present]:
            # Unlike py_trees_ros there is no whole-tree resend to imply the absence
            # of a pruned subtree, so it is stated.
            del self._last_status[gone]
            self._write({"timestamp": timestamp, "behavior_id": str(gone), "removed": True})

    def _write(self, record: dict) -> None:
        json.dump(record, self._file, separators=(",", ":"))
        self._file.write("\n")
        # Flushed per record so a killed or timed-out run keeps what it wrote -- which
        # is exactly the run whose tree state is worth reading.
        self._file.flush()

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
