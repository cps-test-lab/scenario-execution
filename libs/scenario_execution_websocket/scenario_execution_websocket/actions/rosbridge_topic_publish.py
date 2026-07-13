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
from py_trees.common import Status
import roslibpy

from scenario_execution.actions.base_action import BaseAction, ActionError
from scenario_execution_websocket.connection import get_connection, to_rosbridge_type, parse_dict_value


class RosbridgeTopicPublish(BaseAction):
    """
    Publish a message on a ROS topic over the rosbridge protocol.
    """

    def __init__(self, topic_name: str, topic_type: str, host: str, port: int, latch: bool, queue_size: int):
        super().__init__()
        self.topic_name = topic_name
        self.topic_type = topic_type
        self.host = host
        self.port = port
        self.latch = latch
        self.queue_size = queue_size
        self.ros = None
        self.topic = None
        self.msg_to_pub = None

    def setup(self, **kwargs):
        try:
            self.ros = get_connection(self.host, self.port)
            self.topic = roslibpy.Topic(
                self.ros, self.topic_name, to_rosbridge_type(self.topic_type),
                latch=self.latch, queue_size=self.queue_size)
            self.topic.advertise()
        except (ValueError, ConnectionError) as e:
            raise ActionError(f"{e}", action=self) from e

    def execute(self, value: str):
        try:
            self.msg_to_pub = parse_dict_value(value)
        except (ValueError, SyntaxError) as e:
            raise ActionError(f"{e}", action=self) from e

    def update(self) -> py_trees.common.Status:
        self.topic.publish(roslibpy.Message(self.msg_to_pub))
        self.feedback_message = f"published {self.msg_to_pub}"  # pylint: disable= attribute-defined-outside-init
        return Status.SUCCESS

    def shutdown(self):
        if self.topic is not None:
            try:
                self.topic.unadvertise()
            except Exception:  # pylint: disable=broad-except
                pass
