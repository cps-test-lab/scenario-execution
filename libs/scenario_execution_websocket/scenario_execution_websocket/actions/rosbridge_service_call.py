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

from enum import Enum

import py_trees
import roslibpy

from scenario_execution.actions.base_action import BaseAction, ActionError
from scenario_execution.model.types import VariableReference
from scenario_execution_websocket.connection import get_connection, to_rosbridge_type, parse_call_data, get_member


class ServiceCallActionState(Enum):
    """
    States for executing a service call
    """
    IDLE = 1
    SERVICE_CALLED = 2
    DONE = 3
    ERROR = 4


class RosbridgeServiceCall(BaseAction):
    """
    Call a ROS service over the rosbridge protocol.
    """

    def __init__(self, service_name: str, service_type: str, host: str, port: int):
        super().__init__(resolve_variable_reference_arguments_in_execute=False)
        self.service_name = service_name
        self.service_type = service_type
        self.host = host
        self.port = port
        self.ros = None
        self.client = None
        self.data = None
        self.response_variable = None
        self.response_member_name = None
        self.result_message = None
        self.current_state = ServiceCallActionState.IDLE

    def setup(self, **kwargs):
        try:
            self.ros = get_connection(self.host, self.port)
            self.client = roslibpy.Service(self.ros, self.service_name, to_rosbridge_type(self.service_type))
        except (ValueError, ConnectionError) as e:
            raise ActionError(f"{e}", action=self) from e

    def execute(self, data: str, response_variable: str = "", response_member_name: str = ""):
        self.result_message = None
        try:
            self.data = parse_call_data(data)
        except (ValueError, SyntaxError) as e:
            raise ActionError(f"Error while parsing service call data: {e}", action=self) from e

        if response_variable:
            if not isinstance(response_variable, VariableReference):
                raise ActionError("'response_variable' is expected to be a variable reference.", action=self)
            self.response_variable = response_variable
            self.response_member_name = response_member_name

        self.current_state = ServiceCallActionState.IDLE

    def update(self) -> py_trees.common.Status:
        result = py_trees.common.Status.FAILURE
        if self.current_state == ServiceCallActionState.IDLE:
            self.current_state = ServiceCallActionState.SERVICE_CALLED
            self.feedback_message = f"waiting for response from {self.service_name}"  # pylint: disable= attribute-defined-outside-init
            self.client.call(roslibpy.ServiceRequest(self.data), self._done_callback, self._error_callback)
            result = py_trees.common.Status.RUNNING
        elif self.current_state == ServiceCallActionState.SERVICE_CALLED:
            result = py_trees.common.Status.RUNNING
        elif self.current_state == ServiceCallActionState.DONE:
            self.feedback_message = self.result_message or "service response received"  # pylint: disable= attribute-defined-outside-init
            result = py_trees.common.Status.SUCCESS
        else:
            self.feedback_message = f"service call to {self.service_name} failed: {self.result_message}"  # pylint: disable= attribute-defined-outside-init
        return result

    def _done_callback(self, response):
        if self.current_state != ServiceCallActionState.SERVICE_CALLED:
            return
        if self.response_variable is not None:
            try:
                self.response_variable.set_value(get_member(response, self.response_member_name))
            except KeyError as e:
                self.result_message = f"{e}"
                self.current_state = ServiceCallActionState.ERROR
                return
        self.current_state = ServiceCallActionState.DONE

    def _error_callback(self, error):
        self.result_message = f"{error}"
        self.current_state = ServiceCallActionState.ERROR
