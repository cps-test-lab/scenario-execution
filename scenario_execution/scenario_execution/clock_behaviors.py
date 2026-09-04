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

"""Clock-aware replacements for py_trees.timers.Timer and py_trees.decorators.Timeout.

These classes receive a Clock instance via ``kwargs['clock']`` during
``setup()``. When no clock is provided they fall back to WallClock so that
existing scenarios that do not use a SimulationInterface continue to work
without any changes.

These classes are used automatically by ModelToTree when building behavior
trees — user code does not need to instantiate them directly.
"""

import py_trees

from scenario_execution.simulation import Clock, WallClock


class ClockTimer(py_trees.behaviour.Behaviour):
    """Clock-aware replacement for ``py_trees.timers.Timer``.

    Counts *simulated* (or wall-clock) time via a :class:`Clock` instance.
    Behaviour: returns ``RUNNING`` until ``clock.now() >= finish_time``, then
    ``SUCCESS``.

    Args:
        name: Behavior name (typically ``"wait <duration>s"``).
        duration: How many seconds to wait (in clock time).
    """

    def __init__(self, name: str, duration: float):
        super().__init__(name=name)
        if duration < 0.0:
            raise ValueError(f"ClockTimer duration must be non-negative, got {duration}")
        self._duration = duration
        self._clock: Clock = WallClock()
        self._finish_time: float = 0.0

    def setup(self, **kwargs):
        self._clock = kwargs.get('clock', WallClock())

    def initialise(self):
        self._finish_time = self._clock.now() + self._duration

    def update(self):
        if self._clock.now() >= self._finish_time:
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.RUNNING


class ClockTimeout(py_trees.decorators.Decorator):
    """Clock-aware replacement for ``py_trees.decorators.Timeout``.

    Fails the child behavior if it does not succeed within *duration* seconds
    (in clock time).

    Args:
        child: The behavior to decorate.
        name: Decorator name.
        duration: Maximum allowed clock time in seconds.
    """

    def __init__(self, child: py_trees.behaviour.Behaviour, name: str, duration: float):
        super().__init__(child=child, name=name)
        if duration < 0.0:
            raise ValueError(f"ClockTimeout duration must be non-negative, got {duration}")
        self._duration = duration
        self._clock: Clock = WallClock()
        self._finish_time: float = 0.0

    def setup(self, **kwargs):
        self._clock = kwargs.get('clock', WallClock())
        super().setup(**kwargs)

    def initialise(self):
        self._finish_time = self._clock.now() + self._duration

    def update(self):
        if self._clock.now() > self._finish_time:
            self.logger.debug(f"Timeout for {self.decorated.name}")
            self.decorated.stop(py_trees.common.Status.INVALID)
            return py_trees.common.Status.FAILURE
        return self.decorated.status


class _CancelAfterBase(py_trees.decorators.Decorator):
    """Shared timing for the decorators that stop an action after a delay.

    Holds the clock, the deadline and the once-only cancel. Subclasses decide only what the branch
    reports afterwards, which is the whole difference between them:

    ==================  ==========================================
    ``timeout``         the action failed to finish in time
    ``cancel_after``    whatever terminal status the action reports
    ``succeed_after``   done, however far it got
    ==================  ==========================================

    All three stop the action itself; ``timeout`` does so through ``BaseAction.terminate()``.

    Args:
        child: The behavior to decorate.
        name: Decorator name.
        duration: Clock time to wait before cancelling, in seconds.
    """

    def __init__(self, child: py_trees.behaviour.Behaviour, name: str, duration: float):
        super().__init__(child=child, name=name)
        if duration < 0.0:
            raise ValueError(f"{self.__class__.__name__} duration must be non-negative, got {duration}")
        self._duration = duration
        self._clock: Clock = WallClock()
        self._cancel_time: float = 0.0
        self._cancel_sent = False
        self._cancel_refused = False

    def setup(self, **kwargs):
        self._clock = kwargs.get('clock', WallClock())
        super().setup(**kwargs)

    def initialise(self):
        self._cancel_time = self._clock.now() + self._duration
        self._cancel_sent = False
        self._cancel_refused = False

    def _cancel_target(self):
        """The action underneath, looking past any modifiers stacked between us and it.

        Modifiers nest, and the one written last ends up closest to the action, so the decorated
        child is not necessarily the action itself. Asking the nearest child would make the cancel
        depend on the order the modifiers happen to be written in.
        """
        target = self.decorated
        while isinstance(target, py_trees.decorators.Decorator):
            target = target.decorated
        return target

    def _cancel_due(self):
        """Ask the child to stop, once, when its time is up. False if it cannot be cancelled."""
        if self._cancel_refused:
            return False
        if self._cancel_sent or self._clock.now() < self._cancel_time:
            return True

        target = self._cancel_target()
        request_cancel = getattr(target, 'request_cancel', None)
        if request_cancel is None or not request_cancel():
            # Not cancellable: a composite, or an action that never implemented it. Saying so is the
            # point -- a cancel that quietly does nothing leaves the scenario reporting on something
            # it never stopped.
            self.feedback_message = (  # pylint: disable= attribute-defined-outside-init
                f"'{target.name}' ({target.__class__.__name__}) cannot be cancelled")
            self.logger.error(self.feedback_message)
            self._cancel_refused = True
            return False

        self.logger.debug(f"Cancel requested for {self.decorated.name}")
        self._cancel_sent = True
        return True


class CancelAfter(_CancelAfterBase):
    """Cancel the decorated action after *duration*, then report what it makes of that.

    The child keeps ticking after the cancel, so the branch ends on the child's own terminal status.
    That is what lets a scenario assert the outcome of a cancellation -- that a goal really reached
    CANCELED -- rather than merely tolerating the failure a cancelled action would otherwise report.
    """

    def update(self):
        if not self._cancel_due():
            return py_trees.common.Status.FAILURE
        return self.decorated.status


class SucceedAfter(_CancelAfterBase):
    """Stop the decorated action after *duration* and call it done.

    For running something a fixed length of time -- a recording, a background load -- where the
    action has no terminal status worth asserting and would otherwise report the cancel as a
    failure. Success is reported only once a cancel was actually accepted and the child has
    stopped; a child that cannot be cancelled fails instead of being papered over.
    """

    def update(self):
        if not self._cancel_due():
            return py_trees.common.Status.FAILURE
        if not self._cancel_sent:
            # Still within the window. An action that ends early ends the branch on its own terms:
            # a recording that died after five of its thirty seconds did not do what was asked.
            return self.decorated.status
        if self.decorated.status == py_trees.common.Status.RUNNING:
            return py_trees.common.Status.RUNNING
        return py_trees.common.Status.SUCCESS
