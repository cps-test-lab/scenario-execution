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
from scenario_execution_websocket.connection import get_connection, parse_scalar


class ParamActionState(Enum):
    IDLE = 1
    CALLED = 2
    DONE = 3
    ERROR = 4


class RosbridgeSetParameter(BaseAction):
    """
    Set a parameter value via /rosapi.
    """

    def __init__(self, parameter_name: str, host: str, port: int):
        super().__init__()
        self.parameter_name = parameter_name
        self.host = host
        self.port = port
        self.ros = None
        self.param = None
        self.value = None
        self.result_message = None
        self.current_state = ParamActionState.IDLE

    def setup(self, **kwargs):
        try:
            self.ros = get_connection(self.host, self.port)
            self.param = roslibpy.Param(self.ros, self.parameter_name)
        except ConnectionError as e:
            raise ActionError(f"{e}", action=self) from e

    def execute(self, parameter_value: str):
        self.value = parse_scalar(parameter_value)
        self.result_message = None
        self.current_state = ParamActionState.IDLE

    def update(self) -> py_trees.common.Status:
        if self.current_state == ParamActionState.IDLE:
            self.current_state = ParamActionState.CALLED
            self.feedback_message = f"Setting parameter {self.parameter_name} = {self.value}"  # pylint: disable= attribute-defined-outside-init
            self.param.set(self.value, self._callback, self._errback)
            return py_trees.common.Status.RUNNING
        elif self.current_state == ParamActionState.CALLED:
            return py_trees.common.Status.RUNNING
        elif self.current_state == ParamActionState.DONE:
            return py_trees.common.Status.SUCCESS
        self.feedback_message = f"Setting parameter {self.parameter_name} failed: {self.result_message}"  # pylint: disable= attribute-defined-outside-init
        return py_trees.common.Status.FAILURE

    def _callback(self, result):
        if self.current_state == ParamActionState.CALLED:
            self.current_state = ParamActionState.DONE

    def _errback(self, error):
        self.result_message = f"{error}"
        self.current_state = ParamActionState.ERROR
