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
