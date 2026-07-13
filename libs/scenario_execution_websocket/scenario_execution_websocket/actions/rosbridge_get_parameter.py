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
from scenario_execution_websocket.connection import get_connection


class ParamActionState(Enum):
    IDLE = 1
    CALLED = 2
    DONE = 3
    ERROR = 4


class RosbridgeGetParameter(BaseAction):
    """
    Get a parameter value via /rosapi and store it into a variable.
    """

    def __init__(self, parameter_name: str, host: str, port: int):
        super().__init__(resolve_variable_reference_arguments_in_execute=False)
        self.parameter_name = parameter_name
        self.host = host
        self.port = port
        self.ros = None
        self.param = None
        self.target_variable = None
        self.result_message = None
        self.current_state = ParamActionState.IDLE

    def setup(self, **kwargs):
        try:
            self.ros = get_connection(self.host, self.port)
            self.param = roslibpy.Param(self.ros, self.parameter_name)
        except ConnectionError as e:
            raise ActionError(f"{e}", action=self) from e

    def execute(self, target_variable: object):
        if not isinstance(target_variable, VariableReference):
            raise ActionError("'target_variable' is expected to be a variable reference.", action=self)
        self.target_variable = target_variable
        self.result_message = None
        self.current_state = ParamActionState.IDLE

    def update(self) -> py_trees.common.Status:
        if self.current_state == ParamActionState.IDLE:
            self.current_state = ParamActionState.CALLED
            self.feedback_message = f"Getting parameter {self.parameter_name}"  # pylint: disable= attribute-defined-outside-init
            self.param.get(self._callback, self._errback)
            return py_trees.common.Status.RUNNING
        elif self.current_state == ParamActionState.CALLED:
            return py_trees.common.Status.RUNNING
        elif self.current_state == ParamActionState.DONE:
            return py_trees.common.Status.SUCCESS
        self.feedback_message = f"Getting parameter {self.parameter_name} failed: {self.result_message}"  # pylint: disable= attribute-defined-outside-init
        return py_trees.common.Status.FAILURE

    def _callback(self, value):
        if self.current_state != ParamActionState.CALLED:
            return
        self.target_variable.set_value(value)
        self.current_state = ParamActionState.DONE

    def _errback(self, error):
        self.result_message = f"{error}"
        self.current_state = ParamActionState.ERROR
