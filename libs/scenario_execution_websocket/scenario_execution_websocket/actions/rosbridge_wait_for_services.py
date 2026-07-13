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

import py_trees
import roslibpy

from scenario_execution.actions.base_action import BaseAction, ActionError
from scenario_execution_websocket.connection import get_connection


class RosbridgeWaitForServices(BaseAction):
    """
    Wait until all given services are available, queried via /rosapi/services.
    """

    def __init__(self, services: list, host: str, port: int):
        super().__init__()
        self.services = services
        self.host = host
        self.port = port
        self.ros = None
        self.client = None
        self.found = False
        self.query_pending = False

    def setup(self, **kwargs):
        try:
            self.ros = get_connection(self.host, self.port)
            self.client = roslibpy.Service(self.ros, "/rosapi/services", "rosapi/Services")
        except ConnectionError as e:
            raise ActionError(f"{e}", action=self) from e

    def execute(self):
        self.found = False
        self.query_pending = False

    def update(self) -> py_trees.common.Status:
        if self.found:
            return py_trees.common.Status.SUCCESS
        if not self.query_pending:
            self.query_pending = True
            self.client.call(roslibpy.ServiceRequest(), self._callback, self._errback)
        self.feedback_message = f"Waiting for services: {self.services}"  # pylint: disable= attribute-defined-outside-init
        return py_trees.common.Status.RUNNING

    def _callback(self, result):
        available = result['services'] if 'services' in result else result
        self.found = all(service in available for service in self.services)
        self.query_pending = False

    def _errback(self, error):
        self.feedback_message = f"/rosapi/services query failed: {error}"  # pylint: disable= attribute-defined-outside-init
        self.query_pending = False
