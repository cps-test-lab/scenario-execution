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

import time
from enum import Enum

import py_trees
import roslibpy

from scenario_execution.actions.base_action import BaseAction, ActionError
from scenario_execution.model.types import VariableReference
from scenario_execution_websocket.connection import get_connection, to_rosbridge_type, parse_call_data, get_member


class ActionCallActionState(Enum):
    """
    States for executing an action call
    """
    IDLE = 1
    ACTION_CALLED = 2
    DONE = 3
    ERROR = 4


class RosbridgeActionCall(BaseAction):
    """
    Send a ROS2 action goal over the rosbridge v2 protocol.

    rosbridge accepts goals implicitly (there is no explicit acceptance step),
    so ``success_on_acceptance`` succeeds as soon as the goal has been sent.
    """

    def __init__(self, action_name: str, action_type: str, host: str, port: int,
                 success_on_acceptance: bool, timeout: float):
        super().__init__(resolve_variable_reference_arguments_in_execute=False)
        self.action_name = action_name
        self.action_type = action_type
        self.host = host
        self.port = port
        self.success_on_acceptance = success_on_acceptance
        self.timeout = timeout
        self.ros = None
        self.client = None
        self.goal_id = None
        self.data = None
        self.result_variable = None
        self.result_member_name = None
        self.result_message = None
        self.received_feedback = None
        self.start_time = None
        self.current_state = ActionCallActionState.IDLE

    def setup(self, **kwargs):
        try:
            self.ros = get_connection(self.host, self.port)
            self.client = roslibpy.ActionClient(self.ros, self.action_name, to_rosbridge_type(self.action_type))
        except (ValueError, ConnectionError) as e:
            raise ActionError(f"{e}", action=self) from e

    def execute(self, data: str, result_variable: str = "", result_member_name: str = ""):
        try:
            self.data = parse_call_data(data)
        except (ValueError, SyntaxError) as e:
            raise ActionError(f"Error while parsing action goal data: {e}", action=self) from e

        if result_variable:
            if not isinstance(result_variable, VariableReference):
                raise ActionError("'result_variable' is expected to be a variable reference.", action=self)
            self.result_variable = result_variable
            self.result_member_name = result_member_name

        self.received_feedback = None
        self.result_message = None
        self.goal_id = None
        self.start_time = None
        self.current_state = ActionCallActionState.IDLE

    def update(self) -> py_trees.common.Status:
        if self.current_state == ActionCallActionState.IDLE:
            self.start_time = time.time()
            self.goal_id = self.client.send_goal(
                roslibpy.Goal(self.data), self._result_callback, self._feedback_callback, self._error_callback)
            self.current_state = ActionCallActionState.ACTION_CALLED
            self.feedback_message = f"Action {self.action_name} called."  # pylint: disable= attribute-defined-outside-init
            if self.success_on_acceptance:
                return py_trees.common.Status.SUCCESS
            return py_trees.common.Status.RUNNING
        elif self.current_state == ActionCallActionState.ACTION_CALLED:
            if self.timeout and (time.time() - self.start_time) > self.timeout:
                self._cancel()
                self.feedback_message = f"Action {self.action_name} timed out."  # pylint: disable= attribute-defined-outside-init
                return py_trees.common.Status.FAILURE
            if self.received_feedback is not None:
                self.feedback_message = f"Current: {self.received_feedback}"  # pylint: disable= attribute-defined-outside-init
            return py_trees.common.Status.RUNNING
        elif self.current_state == ActionCallActionState.DONE:
            self.feedback_message = "Action successfully finished."  # pylint: disable= attribute-defined-outside-init
            return py_trees.common.Status.SUCCESS
        self.feedback_message = f"Action {self.action_name} failed: {self.result_message}"  # pylint: disable= attribute-defined-outside-init
        return py_trees.common.Status.FAILURE

    def _feedback_callback(self, feedback):
        self.received_feedback = feedback

    def _result_callback(self, result):
        if self.current_state != ActionCallActionState.ACTION_CALLED:
            return
        if self.result_variable is not None:
            try:
                self.result_variable.set_value(get_member(result, self.result_member_name))
            except KeyError as e:
                self.result_message = f"{e}"
                self.current_state = ActionCallActionState.ERROR
                return
        self.current_state = ActionCallActionState.DONE

    def _error_callback(self, error):
        self.result_message = f"{error}"
        self.current_state = ActionCallActionState.ERROR

    def _cancel(self):
        if self.client is not None and self.goal_id is not None:
            try:
                self.client.cancel_goal(self.goal_id)
            except Exception:  # pylint: disable=broad-except
                pass

    def shutdown(self):
        if self.current_state == ActionCallActionState.ACTION_CALLED:
            self._cancel()
