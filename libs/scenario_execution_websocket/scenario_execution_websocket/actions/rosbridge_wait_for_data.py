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
from scenario_execution_websocket.connection import get_connection, to_rosbridge_type


class RosbridgeWaitForData(BaseAction):
    """
    Wait until any message is received on a topic.
    """

    def __init__(self, topic_name: str, topic_type: str, host: str, port: int):
        super().__init__()
        self.topic_name = topic_name
        self.topic_type = topic_type
        self.host = host
        self.port = port
        self.ros = None
        self.topic = None
        self.found = None

    def setup(self, **kwargs):
        try:
            self.ros = get_connection(self.host, self.port)
            self.topic = roslibpy.Topic(self.ros, self.topic_name, to_rosbridge_type(self.topic_type))
            self.topic.subscribe(self._callback)
        except (ValueError, ConnectionError) as e:
            raise ActionError(f"{e}", action=self) from e
        self.feedback_message = f"Waiting for data on {self.topic_name}"  # pylint: disable= attribute-defined-outside-init

    def execute(self):
        self.found = False

    def update(self) -> py_trees.common.Status:
        if self.found is True:
            return py_trees.common.Status.SUCCESS
        return py_trees.common.Status.RUNNING

    def _callback(self, msg):
        if self.found is None:  # do not check until action gets executed
            return
        self.found = True
        self.feedback_message = f"Received data on {self.topic_name}"  # pylint: disable= attribute-defined-outside-init

    def shutdown(self):
        if self.topic is not None:
            try:
                self.topic.unsubscribe()
            except Exception:  # pylint: disable=broad-except
                pass
