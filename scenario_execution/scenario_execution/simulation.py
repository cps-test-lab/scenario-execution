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

"""Clock abstractions and SimulationInterface for step-based simulation support.

The SimulationInterface is designed to be conceptually aligned with the
ros-simulation/simulation_interfaces standard:
  - setup()    -> (sim launch; no direct equivalent in that standard)
  - reset()    -> ResetSimulation service
  - step()     -> StepSimulation service (steps=1) / SimulateSteps action
  - shutdown() -> SetSimulationState(STATE_QUITTING)
"""

import time
from abc import ABC, abstractmethod


class Clock(ABC):
    """Abstract clock used by ClockTimer and ClockTimeout behaviors.

    Provides a unified time source that works for both wallclock and
    step-based simulations.
    """

    @abstractmethod
    def now(self) -> float:
        """Return the current time in seconds."""


class WallClock(Clock):
    """Clock backed by system wall-clock time.

    This is the default clock used when no SimulationInterface is configured.
    Preserves backward compatibility with existing scenarios.
    """

    def now(self) -> float:
        return time.time()


class SimulationClock(Clock):
    """Clock that advances in fixed increments driven by simulation steps.

    Time is defined as: step_count * dt

    The framework creates and manages this clock automatically when a
    SimulationInterface is provided. It is not intended to be advanced
    manually by user code.

    Args:
        dt: Duration of a single simulation step in seconds.
    """

    def __init__(self, dt: float):
        if dt <= 0.0:
            raise ValueError(f"SimulationClock dt must be positive, got {dt}")
        self._dt = dt
        self._step = 0
        self._time = 0.0

    @property
    def dt(self) -> float:
        """Duration of a single simulation step in seconds."""
        return self._dt

    def now(self) -> float:
        """Return the current simulation time in seconds."""
        return self._time

    def advance(self) -> None:
        """Advance the clock by one simulation step (dt seconds).

        Uses integer step counting to avoid floating-point accumulation errors.
        Called internally by the framework once per behavior-tree tick.
        """
        self._step += 1
        self._time = self._step * self._dt

    def reset(self) -> None:
        """Reset the clock to zero.

        Called internally by the framework before each scenario.
        """
        self._step = 0
        self._time = 0.0


class SimulationInterface(ABC):
    """Abstract interface for step-based simulations.

    Implement this class to integrate a custom simulator or system-under-test
    (SUT) with scenario execution. The framework orchestrates the full
    lifecycle: setup → [reset → step...] × N scenarios → shutdown.

    Conceptually aligned with ros-simulation/simulation_interfaces:
      https://github.com/ros-simulation/simulation_interfaces

    **Lifecycle**::

        setup(**kwargs)
        for each scenario:
            reset(scenario_params)  # fully-resolved OSC params, overrides applied
            while scenario running:
                step()          # advance simulation by dt
                tick()          # advance behavior tree
        shutdown()

    **Accessing the simulation from behaviors**:

    Behaviors receive the simulation object via ``kwargs['simulation']`` in
    their ``setup()`` method — the same pattern as ROS behaviors using
    ``kwargs['node']``::

        class MyAction(BaseAction):
            def setup(self, **kwargs):
                self.sim = kwargs['simulation']

            def update(self):
                obs = self.sim.get_observation()
                ...

    **Example**::

        class MuJoCoSim(SimulationInterface):
            def __init__(self, model_path: str):
                self._model_path = model_path
                self._model = None
                self._data = None

            @property
            def dt(self) -> float:
                return 0.002  # 500 Hz

            def setup(self, **kwargs) -> None:
                import mujoco
                self._model = mujoco.MjModel.from_xml_path(self._model_path)
                self._data = mujoco.MjData(self._model)

            def reset(self) -> None:
                import mujoco
                mujoco.mj_resetData(self._model, self._data)

            def step(self) -> None:
                import mujoco
                mujoco.mj_step(self._model, self._data)

            def shutdown(self) -> None:
                self._model = None
                self._data = None
    """

    @property
    @abstractmethod
    def dt(self) -> float:
        """Duration of a single simulation step in seconds.

        The framework uses this value to:
        - Set the behavior-tree tick period
        - Create a SimulationClock so that ``wait elapsed(1s)`` maps to
          exactly ``1 / dt`` simulation steps
        """

    def setup(self, **kwargs) -> None:
        """Initialize the simulation. Called once before any scenario runs.

        Args:
            **kwargs: Same keyword arguments passed to behavior ``setup()``
                methods, including ``logger``, ``output_dir``, ``tick_period``.
                Additional simulator-specific arguments can be ignored.

        This is the right place to load world files, connect to a simulator
        process, allocate resources, etc.

        Analogous to ``LoadWorld`` + simulator launch in simulation_interfaces.
        """

    def reset(self, **kwargs) -> None:
        """Reset simulation state for a new scenario.

        Called before each scenario. Any OSC scenario parameters that match
        argument names in the concrete ``reset()`` override are injected
        automatically. Declare only the parameters you actually need::

            def reset(self, initial_velocity, gravity=9.81):
                self._robot.set_velocity(initial_velocity)
                self._world.set_gravity(gravity)

        The framework validates that every required argument (no default) is
        declared in the OSC scenario file and raises an error early if any are
        missing. Optional arguments (with defaults) are passed when present in
        the scenario, or fall back to their default otherwise.

        Override via ``--scenario-parameter-file`` is already applied before
        this method is called, so no special handling is needed.

        Must NOT tear down the simulation (that is ``shutdown()``'s job). The
        simulation clock is reset separately by the framework.

        Analogous to ``ResetSimulation`` in simulation_interfaces, with an
        implicit scope of SCOPE_ALL (time + state + spawned entities).
        """

    @abstractmethod
    def step(self) -> None:
        """Advance the simulation by one timestep (``dt`` seconds).

        Called once per behavior-tree tick, before the tree is ticked.
        Must be non-blocking.

        Analogous to ``StepSimulation(steps=1)`` in simulation_interfaces.
        """

    def shutdown(self) -> None:
        """Tear down the simulation. Called once after all scenarios complete.

        Analogous to ``SetSimulationState(STATE_QUITTING)`` in
        simulation_interfaces.
        """
