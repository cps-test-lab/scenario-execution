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

"""Record how fast the tree actually ticked, and where the time went.

Two CSV files, written side by side:

* ``tick_timing.csv`` -- one row per tick: the interval since the previous tick,
  how long the tick itself took, and the *configured* period it was aiming for.
  ``interval_s / period_s`` is the achieved-against-intended ratio, dimensionless,
  so a fast and a slow machine read the same way.
* ``action_timing.csv`` -- one row per timed action call (``setup``, ``execute``,
  ``update``), so a tick that ran long can be attributed to the action that spent
  the time. Equally usable on its own to profile a slow action.

TIMING ONLY. Nothing here reads process CPU time, psutil or a cgroup file --
resource accounting is a separate concern with separate tooling. That still
separates the two cases worth separating, by *where* the time went rather than
what consumed it:

* a large ``interval_s`` while the previous tick's ``duration_s`` is small and no
  action row accounts for the gap -- time passed BETWEEN ticks, nothing running;
* a large ``duration_s`` with action rows summing to most of it -- time spent
  INSIDE the tick, doing work, by an action this names.

The one case timing alone cannot separate: time lost between ticks to another
callback on the same callback group looks exactly like not being scheduled.
Telling those apart needs a resource signal, which belongs to whatever consumes
these files and can join them on ``wall_ts``.

Compatible with the behaviour-tree log by construction: ``behavior_id``,
``behavior_name``, ``class_name`` and ``status`` are spelled and produced exactly
as :mod:`scenario_execution.utils.bt_logger` spells and produces them, and
``timestamp`` comes from the same clock with the same semantics. So the files join
on ``behavior_id`` without either being translated into the other's terms. They
stay separate files because the behaviour log writes only on status change -- it
is silent across exactly the window a stall occupies -- and its timeline is
simulated time, which hides scheduling delay entirely.

Identity is repeated per row rather than referenced, because the two features are
independently enabled and this file must be readable when it is the only one
written.

Cost, which is the condition this design has to meet: the call path does no
formatting and no I/O. A tick costs two ``time.monotonic()`` reads; a timed action
call costs two more plus one ``list.append``. Rows are serialised in a flush that
runs at most once per wall second. Nothing is installed at all unless recording is
enabled -- see :meth:`ScenarioExecution._setup_tick_recorder`.
"""

import csv
import os
import time

import py_trees

TICK_FILENAME = "tick_timing.csv"
ACTION_FILENAME = "action_timing.csv"

TICK_FIELDS = ("tick", "wall_ts", "timestamp", "interval_s", "duration_s", "period_s", "driver")
ACTION_FIELDS = ("tick", "wall_ts", "timestamp", "behavior_id", "behavior_name",
                 "class_name", "phase", "duration_s", "status")

#: Wall seconds between flushes. A killed run keeps everything up to the last one.
FLUSH_INTERVAL = 1.0

#: How the tree is being ticked. Recorded per row because it decides whether
#: ``interval_s`` means anything: the step-based loop is unpaced, so its interval
#: describes how fast the machine ran, not whether a rate was held.
DRIVER_WALL_LOOP = "wall_loop"
DRIVER_ROS_TIMER = "ros_timer"
DRIVER_SIM_STEP = "sim_step"

#: The three calls that are timed. ``execute`` is the activation call
#: (``initialise()``), which for an action carries its argument resolution and
#: its ``execute()``; it is one-shot, and named apart from ``update`` so a
#: one-off cost is never read as a per-tick one.
PHASE_SETUP = "setup"
PHASE_EXECUTE = "execute"
PHASE_UPDATE = "update"


def _fmt(value) -> str:
    """Seconds with microsecond resolution; empty for a value that does not exist.

    Empty rather than ``0`` on purpose: no preceding tick and a zero-length
    interval are different facts, and a zero would read as an infinitely fast tick.
    """
    return "" if value is None else f"{value:.6f}"


class ActionTimings:
    """Per-call timings for the actions of one scenario.

    Wrappers are installed on instances by :meth:`TickRecorder.install_on_tree`,
    never at class-definition time, so an action in a run that did not ask for
    recording is untouched -- no wrapper, no branch, no attribute.
    """

    def __init__(self, recorder):
        self._recorder = recorder
        self.rows = []

    def wrap(self, func, behaviour, ident, phase):
        """Return *func* wrapped so its duration is recorded under *phase*.

        The closure captures the identity resolved once at install time, so the
        call path does no lookup: two clock reads, one append.

        Two closures rather than one with a branch, because ``update`` has to read
        the status differently. py_trees assigns ``behaviour.status`` only *after*
        ``update()`` returns, so reading the attribute in the wrapper would record
        the status the action had before the call -- every first tick would say
        INVALID. The returned value is the status the call produced, so ``update``
        takes it from there. The other phases do not return one and read the
        attribute, which by then is correct.
        """
        rows = self.rows
        context = self._recorder.tick_context
        monotonic = time.monotonic

        if phase == PHASE_UPDATE:
            def timed(*args, **kwargs):
                start = monotonic()
                status = None
                try:
                    status = func(*args, **kwargs)
                    return status
                finally:
                    duration = monotonic() - start
                    tick, wall_ts, timestamp = context()
                    rows.append((tick, wall_ts, timestamp, ident[0], ident[1], ident[2],
                                 phase, duration,
                                 behaviour.status.name if status is None else status.name))
        else:
            def timed(*args, **kwargs):
                start = monotonic()
                try:
                    return func(*args, **kwargs)
                finally:
                    duration = monotonic() - start
                    tick, wall_ts, timestamp = context()
                    rows.append((tick, wall_ts, timestamp, ident[0], ident[1], ident[2],
                                 phase, duration, behaviour.status.name))

        timed.scenario_execution_timing_wrapper = True
        return timed


class TickRecorder:
    """Writes both timing files for one scenario.

    Lifecycle mirrors :class:`~scenario_execution.utils.bt_logger.BehaviourTreeJsonlLogger`:
    the constructor opens the files and writes their headers immediately, the
    instance is a post-tick handler, and :meth:`close` flushes what is buffered.

    The headers are written before the first tick on purpose. A run whose tree
    never ticked then leaves a header and no rows -- measured, and empty -- which
    is a different statement from leaving no file at all.
    """

    def __init__(self, output_dir, tick_period, driver, clock=None, start_epoch=None):
        # Kept so the summary is read back from the directory this instance wrote,
        # rather than from wherever the runner has moved on to since.
        self.output_dir = output_dir
        self.tick_period = tick_period
        self.driver = driver
        self._clock = clock
        self._monotonic_start = time.monotonic()
        self._start_epoch = time.time() if start_epoch is None else start_epoch
        self._tick_start = None
        self._prev_tick_start = None
        self._tick = None
        self._tick_wall_ts = None
        self._tick_timestamp = None
        self._last_flush = self._monotonic_start
        self._tick_rows = []
        self.actions = ActionTimings(self)

        self._tick_file = open(os.path.join(output_dir, TICK_FILENAME),  # pylint: disable=consider-using-with
                               "w", encoding="utf-8", newline="")
        self._tick_writer = csv.writer(self._tick_file)
        self._tick_writer.writerow(TICK_FIELDS)
        self._tick_file.flush()

        self._action_file = open(os.path.join(output_dir, ACTION_FILENAME),  # pylint: disable=consider-using-with
                                 "w", encoding="utf-8", newline="")
        self._action_writer = csv.writer(self._action_file)
        self._action_writer.writerow(ACTION_FIELDS)
        self._action_file.flush()

    @property
    def closed(self) -> bool:
        return self._tick_file is None

    def now(self) -> float:
        """Seconds since the scenario started -- simulated time when a clock is given.

        Identical to the behaviour log's definition, from the same clock, so a
        record there and a row here for the same moment carry the same number.
        """
        if self._clock is not None:
            return self._clock.now()
        return time.monotonic() - self._monotonic_start

    def wall_ts(self) -> float:
        """Epoch seconds, advanced by the monotonic clock.

        Epoch-valued so a consumer can line these rows up with anything else
        recorded during the run, but derived from ``monotonic()`` so a step of the
        system clock mid-run cannot make the series go backwards.
        """
        return self._start_epoch + (time.monotonic() - self._monotonic_start)

    def tick_context(self):
        """``(tick, wall_ts, timestamp)`` for the tick in progress.

        Action rows are stamped with the tick's context rather than their own, so
        every call made during a tick shares its timestamp and joins the tick row
        exactly. Before the first tick -- where bring-up ``setup`` lands -- there is
        no tick to belong to, so the tick number is empty and the moment is taken
        directly.
        """
        if self._tick is None:
            return "", _fmt(self.wall_ts()), _fmt(self.now())
        return self._tick, self._tick_wall_ts, self._tick_timestamp

    def pre_tick_handler(self, behaviour_tree) -> None:
        """Stamp the start of the tick.

        Its own handler rather than a branch inside the existing one, so a run
        without recording keeps exactly the handler set it has today.
        """
        self._prev_tick_start = self._tick_start
        self._tick_start = time.monotonic()
        # 1-based: py_trees increments ``count`` only after the post-tick handlers,
        # so during the first tick it still reads 0. Recorded as "how many ticks have
        # happened including this one", which is what a reader of the row means.
        self._tick = behaviour_tree.count + 1
        self._tick_wall_ts = _fmt(self._start_epoch + (self._tick_start - self._monotonic_start))
        self._tick_timestamp = _fmt(self.now())

    def __call__(self, behaviour_tree) -> None:
        """Post-tick handler: close out the tick row and flush if due."""
        if self._tick_file is None:
            return
        end = time.monotonic()
        interval = None if self._prev_tick_start is None else self._tick_start - self._prev_tick_start
        self._tick_rows.append((self._tick, self._tick_wall_ts, self._tick_timestamp,
                                _fmt(interval), _fmt(end - self._tick_start),
                                _fmt(self.tick_period), self.driver))
        if end - self._last_flush >= FLUSH_INTERVAL:
            self._last_flush = end
            self.flush()

    def install_on_tree(self, behaviour_tree) -> None:
        """Install timing wrappers on every leaf of *behaviour_tree*.

        Called once before the tree is set up -- so each leaf's own ``setup()`` cost
        is captured -- and again whenever the tree changes shape.

        Every leaf, not only the actions from the action libraries. A scenario's
        ``wait elapsed()`` becomes a ``ClockTimer`` and its ``emit`` a
        ``TopicPublish``; neither derives from ``BaseAction``, and covering only
        what does would leave most of a typical tree unmeasured. Attribution that
        cannot see a whole class of node does not merely miss time, it blames the
        wrong node for it.

        Composites are skipped: they route ticks rather than do work, and a row per
        composite per tick would grow the file for nothing. Their children are
        ticked from ``Composite.tick()`` rather than from ``update()``, so nothing
        is double-counted by leaving them out.

        Wrappers are set on the *instance*. Nothing is installed on any class, so a
        run without recording sees the behaviours exactly as they are defined.
        """
        for behaviour in behaviour_tree.root.iterate():
            if isinstance(behaviour, py_trees.composites.Composite):
                continue
            if getattr(behaviour, "_scenario_execution_timed", False):
                continue
            behaviour._scenario_execution_timed = True  # pylint: disable=protected-access
            # Identity resolved once, here, and captured by the wrappers, so a timed
            # call does no lookup. Spelled exactly as the behaviour-tree log spells
            # it, so the two records join.
            ident = (str(behaviour.id), behaviour.name,
                     py_trees.utilities.get_fully_qualified_name(behaviour))
            behaviour.setup = self.actions.wrap(behaviour.setup, behaviour, ident, PHASE_SETUP)
            behaviour.initialise = self.actions.wrap(
                behaviour.initialise, behaviour, ident, PHASE_EXECUTE)
            behaviour.update = self.actions.wrap(behaviour.update, behaviour, ident, PHASE_UPDATE)

    def watch_tree_updates(self, behaviour_tree) -> None:
        """Pick up actions inserted after setup, without walking the tree per tick.

        py_trees calls ``tree_update_handler`` from ``insert_subtree`` /
        ``replace_subtree`` / ``prune_subtree`` and nowhere else, so a walk happens
        only when the tree actually changed shape. It is a single callable slot
        rather than a handler list, so any existing handler is chained, not lost.
        """
        previous = behaviour_tree.tree_update_handler

        def on_update():
            if previous is not None:
                previous()
            self.install_on_tree(behaviour_tree)

        behaviour_tree.tree_update_handler = on_update

    def flush(self) -> None:
        if self._tick_file is None:
            return
        if self._tick_rows:
            self._tick_writer.writerows(self._tick_rows)
            self._tick_rows.clear()
            self._tick_file.flush()
        action_rows = self.actions.rows
        if action_rows:
            self._action_writer.writerows(
                (tick, wall_ts, timestamp, behavior_id, behavior_name, class_name,
                 phase, _fmt(duration), status)
                for tick, wall_ts, timestamp, behavior_id, behavior_name, class_name,
                phase, duration, status in action_rows)
            action_rows.clear()
            self._action_file.flush()

    def close(self) -> None:
        self.flush()
        if self._tick_file is not None:
            self._tick_file.close()
            self._tick_file = None
        if self._action_file is not None:
            self._action_file.close()
            self._action_file = None
