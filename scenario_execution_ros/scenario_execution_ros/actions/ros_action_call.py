# Copyright (C) 2025 Frederik Pasch
# Copyright (C) 2024 Intel Corporation
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

from ast import literal_eval
from enum import Enum
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, DurabilityPolicy
from rosidl_runtime_py.set_message import set_message_fields
import py_trees  # pylint: disable=import-error
from action_msgs.msg import GoalStatus
from scenario_execution.actions.base_action import BaseAction, ActionError
from scenario_execution.simulation import Clock, WallClock
from scenario_execution import ShutdownHandler
from scenario_execution.model.types import VariableReference
from scenario_execution_ros.actions.conversions import get_ros_message_type, set_variable_if_available


_STATUS_NAMES = {
    GoalStatus.STATUS_SUCCEEDED: "succeeded",
    GoalStatus.STATUS_CANCELED: "canceled",
    GoalStatus.STATUS_ABORTED: "aborted",
}


def _status_name(status):
    """The osc name for a GoalStatus, so a message reads like the scenario that asked for it."""
    return _STATUS_NAMES.get(status, f"status {status}")


class ActionCallActionState(Enum):
    """
    States for executing a service call
    """
    IDLE = 1
    ACTION_SERVER_AVAILABLE = 2
    ACTION_CALLED = 3
    ACTION_ACCEPTED = 4
    ACTION_CANCELING = 5
    DONE = 6
    ERROR = 7


class RosActionCall(BaseAction):
    """
    ros service call behavior
    """

    def __init__(self, action_name: str, action_type: str, success_on_acceptance: bool = False, transient_local: bool = False,
                 expected_status=("succeeded", GoalStatus.STATUS_SUCCEEDED), cancel_after: float = -1.0):
        super().__init__(resolve_variable_reference_arguments_in_execute=False)
        self.node = None
        self.client = None
        self.send_goal_future = None
        self.goal_handle = None
        self.action_type_string = action_type
        self.action_type = None
        self.action_name = action_name
        self.received_feedback = None
        self.data = None
        self.current_state = ActionCallActionState.IDLE
        self.cb_group = ReentrantCallbackGroup()
        self.success_on_acceptance = success_on_acceptance
        self.transient_local = transient_local
        self.result_variable = None
        self.result_variable_member_name = None
        # An osc enum arrives as (name, value); the enum's values are the GoalStatus constants, so
        # the comparison in get_result_callback() is against the status the server actually reports.
        self.expected_status = expected_status[1] if isinstance(expected_status, tuple) else expected_status
        #: Negative disables it. The goal is cancelled this long after it is sent, and the action
        #: then waits for the terminal status instead of ending, which is what lets expected_status
        #: assert that the cancellation was honoured.
        self.cancel_after = cancel_after
        self.cancel_deadline = None
        self.clock: Clock = WallClock()
        #: A cancel can be asked for before there is a goal to cancel, so the request is recorded
        #: here and _send_cancel() acts on it as soon as the goal is accepted.
        self.cancel_requested = False
        self.cancel_sent = False

    def setup(self, **kwargs):
        """
        Setup ROS2 node and action client

        """
        self.clock = kwargs.get('clock', WallClock())
        try:
            self.node: Node = kwargs['node']
        except KeyError as e:
            error_message = "didn't find 'node' in setup's kwargs [{}][{}]".format(
                self.name, self.__class__.__name__)
            raise ActionError(error_message, action=self) from e

        self.action_type = get_ros_message_type(self.action_type_string)

        client_kwargs = {
            "callback_group": self.cb_group,
        }

        if self.transient_local:
            qos_profile = QoSProfile(depth=1)
            qos_profile.durability = DurabilityPolicy.TRANSIENT_LOCAL
            client_kwargs["result_service_qos_profile"] = qos_profile

        self.client = ActionClient(self.node, self.action_type, self.action_name, **client_kwargs)

    def execute(self, data: str, result_variable: str = "", result_member_name: str = ""):
        self.parse_data(data)

        if result_variable:
            if not isinstance(result_variable, VariableReference):
                raise ActionError(f"'response_variable' is expected to be a variable reference.", action=self)
            self.result_variable = result_variable
            self.result_variable_member_name = result_member_name

        if self.success_on_acceptance and self.expected_status != GoalStatus.STATUS_SUCCEEDED:
            # success_on_acceptance finishes the action the moment the goal is accepted, before any
            # terminal status exists. Asking for a particular one as well cannot be honoured.
            raise ActionError(
                "'expected_status' cannot be combined with 'success_on_acceptance': the action "
                "finishes at goal acceptance, before the goal reaches any status.", action=self)

        self.cancel_requested = False
        self.cancel_sent = False
        self.cancel_deadline = None
        self.current_state = ActionCallActionState.IDLE

    def parse_data(self, data):
        if data:
            try:
                trimmed_data = data.encode('utf-8').decode('unicode_escape')
                self.data = literal_eval(trimmed_data)
            except Exception as e:  # pylint: disable=broad-except
                raise ActionError(f"Error while parsing sevice call data:", action=self) from e

    def update(self) -> py_trees.common.Status:
        """
        Execute states
        """
        self.logger.debug(f"Current State {self.current_state}")
        if self.cancel_deadline is not None and self.clock.now() >= self.cancel_deadline:
            self.cancel_deadline = None
            self.request_cancel()
        result = py_trees.common.Status.FAILURE
        if self.current_state == ActionCallActionState.IDLE:
            if self.client.wait_for_server(0.0):
                self.current_state = ActionCallActionState.ACTION_SERVER_AVAILABLE
            result = py_trees.common.Status.RUNNING
        elif self.current_state == ActionCallActionState.ACTION_SERVER_AVAILABLE:
            self.current_state = ActionCallActionState.ACTION_CALLED
            if self.send_goal_future:
                self.send_goal_future.cancel()
            self.send_goal_future = self.client.send_goal_async(self.get_goal_msg(), feedback_callback=self.feedback_callback)
            self.send_goal_future.add_done_callback(self.goal_response_callback)
            if self.cancel_after >= 0:
                self.cancel_deadline = self.clock.now() + self.cancel_after
            result = py_trees.common.Status.RUNNING
        elif self.current_state == ActionCallActionState.ACTION_CALLED:
            result = py_trees.common.Status.RUNNING
        elif self.current_state == ActionCallActionState.ACTION_ACCEPTED:
            if self.success_on_acceptance:
                return py_trees.common.Status.SUCCESS
            result = py_trees.common.Status.RUNNING
        elif self.current_state == ActionCallActionState.ACTION_CANCELING:
            result = py_trees.common.Status.RUNNING
        elif self.current_state == ActionCallActionState.DONE:
            result = py_trees.common.Status.SUCCESS
        elif self.current_state == ActionCallActionState.ERROR:
            result = py_trees.common.Status.FAILURE
        else:
            self.logger.error(f"Invalid state {self.current_state}")
        feedback_msg = self.get_feedback_message(self.current_state)
        if feedback_msg is not None:
            self.feedback_message = feedback_msg  # pylint: disable= attribute-defined-outside-init

        return result

    def get_goal_msg(self):
        req = self.action_type.Goal()
        set_message_fields(req, self.data)
        return req

    def feedback_callback(self, msg):
        self.received_feedback = msg.feedback

    def goal_response_callback(self, future):
        self.goal_handle = future.result()
        if not self.goal_handle.accepted:
            self.feedback_message = f"Goal rejected."  # pylint: disable= attribute-defined-outside-init
            self.current_state = ActionCallActionState.ERROR
            return
        self.current_state = ActionCallActionState.ACTION_ACCEPTED
        self.feedback_message = f"Goal accepted."  # pylint: disable= attribute-defined-outside-init
        if not self.success_on_acceptance:
            get_result_future = self.goal_handle.get_result_async()
            get_result_future.add_done_callback(self.get_result_callback)
        # A cancel asked for while the goal was still being accepted has been waiting for this.
        self._send_cancel()

    def get_result_callback(self, future):
        """
        Callback function when the action future is done
        """
        status = future.result().status
        self.logger.debug(f"Received state {status}")
        if self.current_state in (ActionCallActionState.ACTION_ACCEPTED, ActionCallActionState.ACTION_CANCELING):
            self.goal_handle = None
            if status == self.expected_status:
                self.current_state = ActionCallActionState.DONE
                if status == GoalStatus.STATUS_SUCCEEDED:
                    set_variable_if_available(future.result().result, self.result_variable, self.result_variable_member_name)
                self.feedback_message = f"Goal {_status_name(status)}."   # pylint: disable= attribute-defined-outside-init
            else:
                self.current_state = ActionCallActionState.ERROR
                self.feedback_message = (  # pylint: disable= attribute-defined-outside-init
                    f"Goal {_status_name(status)}, expected {_status_name(self.expected_status)}.")
        else:
            if not self.success_on_acceptance:
                self.current_state = ActionCallActionState.ERROR

    def request_cancel(self) -> bool:
        self.cancel_requested = True
        self._send_cancel()
        return True

    def _send_cancel(self):
        """Send the cancel if there is a goal to send it for. Returns the future, or None.

        A cancel can be asked for before the goal has been accepted, and before then there is no
        handle to cancel. The request is kept and goal_response_callback() calls this again, so a
        cancel that arrives early still reaches the server instead of being dropped.
        """
        if not self.cancel_requested or self.cancel_sent or self.goal_handle is None:
            return None

        self.cancel_sent = True
        self.current_state = ActionCallActionState.ACTION_CANCELING
        self.feedback_message = f"Canceling goal on {self.action_name}."  # pylint: disable= attribute-defined-outside-init
        return self.goal_handle.cancel_goal_async()

    def shutdown(self):
        self.cancel_requested = True
        future = self._send_cancel()
        if future is not None:
            shutdown_handler = ShutdownHandler.get_instance()
            shutdown_handler.add_future(future)

    def get_feedback_message(self, current_state):
        feedback_message = None
        if current_state == ActionCallActionState.IDLE:
            feedback_message = f"Waiting for action server {self.action_name}"
        elif current_state == ActionCallActionState.ACTION_ACCEPTED:
            if self.received_feedback is not None:
                feedback_message = f"Current: {self.received_feedback}"
            else:
                feedback_message = f"Action {self.action_name} called."
        elif current_state == ActionCallActionState.DONE:
            if self.expected_status == GoalStatus.STATUS_SUCCEEDED:
                feedback_message = f"Action successfully finished."
            else:
                # The action passed by ending the way the scenario said it should, which is not the
                # same as the goal succeeding -- saying "successfully finished" would misreport a
                # goal that was canceled or aborted on purpose.
                feedback_message = f"Action finished as expected: goal {_status_name(self.expected_status)}."
        return feedback_message
