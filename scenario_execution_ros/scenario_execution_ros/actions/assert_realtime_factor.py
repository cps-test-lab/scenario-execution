# Copyright (C) 2025 Frederik Pasch
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


from collections import deque
import time
import py_trees  # pylint: disable=import-error
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from scenario_execution_ros.actions.conversions import get_comparison_operator, get_qos_preset_profile
from scenario_execution.actions.base_action import BaseAction, ActionError


class AssertRealtimeFactor(BaseAction):
    """Compare the rate of the ROS clock against wall time.

    Subscribes ``/clock`` directly instead of reading ``node.get_clock()``, so the measurement does not
    depend on whether the scenario execution node runs with ``use_sim_time`` and works against any
    simulator publishing sim time.
    """

    def __init__(self):
        super().__init__()
        self.realtime_factor = None
        self.comparison_operator = None
        self.comparison_operator_feedback = None
        self.rolling_average_count = None
        self.grace_period = None
        self.grace_start = None
        self.node = None
        self.subscription = None
        self.prev_sim = None
        self.prev_wall = None
        self.delta_sim = None
        self.delta_wall = None
        self.average_factor = None

    def setup(self, **kwargs):
        try:
            self.node: Node = kwargs['node']
        except KeyError as e:
            error_message = "didn't find 'node' in setup's kwargs [{}][{}]".format(
                self.name, self.__class__.__name__)
            raise ActionError(error_message, action=self) from e

        self.subscription = self.node.create_subscription(
            msg_type=Clock,
            topic='/clock',
            callback=self._callback,
            qos_profile=get_qos_preset_profile(['sensor_data'])
        )

    def execute(self, realtime_factor: float, comparison_operator: bool, rolling_average_count: int, grace_period: float):
        if rolling_average_count < 1:
            raise ActionError(f"rolling_average_count must be >= 1, got {rolling_average_count}.", action=self)
        self.realtime_factor = realtime_factor
        self.comparison_operator_feedback = comparison_operator[0]
        self.comparison_operator = get_comparison_operator(comparison_operator)
        self.rolling_average_count = rolling_average_count
        self.grace_period = grace_period
        self.grace_start = time.monotonic()
        self.delta_sim = deque(maxlen=rolling_average_count)
        self.delta_wall = deque(maxlen=rolling_average_count)
        self.prev_sim = None
        self.prev_wall = None
        self.average_factor = None

    def update(self) -> py_trees.common.Status:
        if self.in_grace_period():
            remaining = self.grace_period - (time.monotonic() - self.grace_start)
            self.feedback_message = f"Grace period, {remaining:.1f} s remaining"
            return py_trees.common.Status.RUNNING

        # Deliberately no verdict on a partially filled window: averaging fewer samples than requested
        # would defeat the smoothing rolling_average_count exists to provide. A silent /clock therefore
        # keeps the action RUNNING; detecting a dead simulator is a separate concern.
        samples = len(self.delta_wall)
        if samples < self.rolling_average_count:
            self.feedback_message = f"Waiting for /clock samples ({samples}/{self.rolling_average_count})"
            return py_trees.common.Status.RUNNING

        expected = f'{self.comparison_operator_feedback} {self.realtime_factor}'
        if self.comparison_operator(self.average_factor, self.realtime_factor):
            self.feedback_message = f'Realtime factor within range: expected {expected}, actual {self.average_factor:.3f}'
            return py_trees.common.Status.RUNNING

        self.feedback_message = f'Realtime factor not within range: expected {expected}, actual {self.average_factor:.3f}'
        return py_trees.common.Status.FAILURE

    def in_grace_period(self):
        return self.grace_start is not None and (time.monotonic() - self.grace_start) < self.grace_period

    def reset_window(self):
        self.delta_sim.clear()
        self.delta_wall.clear()
        self.average_factor = None

    def _callback(self, msg):
        sim_now = msg.clock.sec + msg.clock.nanosec * 1e-9
        wall_now = time.monotonic()  # monotonic, not time.time(): a rate must not be perturbed by clock steps

        if self.grace_start is None:  # message arrived before execute() set up the window
            return

        prev_sim, prev_wall = self.prev_sim, self.prev_wall
        self.prev_sim, self.prev_wall = sim_now, wall_now

        if self.in_grace_period():
            # Accumulating during bring-up would leave the window full of exactly the samples the grace
            # period exists to ignore, failing the moment it ends.
            self.reset_window()
            return

        if prev_sim is None:
            return

        delta_sim = sim_now - prev_sim
        delta_wall = wall_now - prev_wall
        if delta_wall <= 0.:
            return
        if delta_sim < 0.:  # clock jumped backwards, the simulation was reset
            self.reset_window()
            return

        self.delta_sim.append(delta_sim)
        self.delta_wall.append(delta_wall)
        if len(self.delta_wall) == self.rolling_average_count:
            # The realtime factor over the window is the ratio of the sums, not the mean of the
            # per-sample ratios: /clock arrives at a fixed sim-time step, so a single short wall
            # interval would otherwise dominate the mean and mask a genuine slowdown.
            self.average_factor = sum(self.delta_sim) / sum(self.delta_wall)
