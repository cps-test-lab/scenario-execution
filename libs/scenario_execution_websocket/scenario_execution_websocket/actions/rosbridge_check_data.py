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

from ast import literal_eval

import py_trees
import roslibpy

from scenario_execution.actions.base_action import BaseAction, ActionError
from scenario_execution_websocket.connection import get_connection, to_rosbridge_type, get_comparison_operator, get_member


class RosbridgeCheckData(BaseAction):
    """
    Compare received topic messages using comparison_operator against expected_value.

    Either the whole message dict is compared, or the member selected by
    member_name.
    """

    def __init__(self, topic_name: str, topic_type: str, member_name: str, host: str, port: int):
        super().__init__()
        self.topic_name = topic_name
        self.topic_type = topic_type
        self.member_name = member_name
        self.host = host
        self.port = port
        self.expected_value = None
        self.comparison_operator = None
        self.fail_if_no_data = None
        self.fail_if_bad_comparison = None
        self.wait_for_first_message = None
        self.last_msg = None
        self.found = None
        self.comparison_text = ""
        self.ros = None
        self.topic = None

    def setup(self, **kwargs):
        try:
            self.ros = get_connection(self.host, self.port)
            self.topic = roslibpy.Topic(self.ros, self.topic_name, to_rosbridge_type(self.topic_type))
            self.topic.subscribe(self._callback)
        except (ValueError, ConnectionError) as e:
            raise ActionError(f"{e}", action=self) from e
        self.feedback_message = f"Waiting for data on {self.topic_name}"  # pylint: disable= attribute-defined-outside-init

    def execute(self,
                expected_value: str,
                eval_expected_value: bool,
                comparison_operator: tuple,
                fail_if_no_data: bool,
                fail_if_bad_comparison: bool,
                wait_for_first_message: bool):
        self.set_expected_value(expected_value, eval_expected_value)
        self.comparison_operator = get_comparison_operator(comparison_operator)
        self.fail_if_no_data = fail_if_no_data
        self.fail_if_bad_comparison = fail_if_bad_comparison
        self.wait_for_first_message = wait_for_first_message
        self.found = None
        if not wait_for_first_message:
            self.check_data(self.last_msg)
            if self.found is True:
                self.feedback_message = "Found expected value in previously received message."  # pylint: disable= attribute-defined-outside-init

    def update(self) -> py_trees.common.Status:
        if self.found is True:
            return py_trees.common.Status.SUCCESS
        elif self.found is False:
            if self.fail_if_bad_comparison:
                return py_trees.common.Status.FAILURE
        elif self.last_msg is None and self.fail_if_no_data:
            return py_trees.common.Status.FAILURE
        return py_trees.common.Status.RUNNING

    def _callback(self, msg):
        self.last_msg = msg
        self.check_data(msg)
        if self.found is True:
            self.feedback_message = "Found expected value in received message."  # pylint: disable= attribute-defined-outside-init
        else:
            self.feedback_message = f"Received message does not contain expected value. Check: {self.comparison_text}"  # pylint: disable= attribute-defined-outside-init

    def check_data(self, msg):
        if msg is None or self.expected_value is None:
            return
        try:
            value = get_member(msg, self.member_name)
        except KeyError:
            self.feedback_message = f"Member name not found {self.member_name}"  # pylint: disable= attribute-defined-outside-init
            return
        self.comparison_text = f"{value} {self.comparison_operator.__name__} {self.expected_value}"
        self.found = self.comparison_operator(value, self.expected_value)

    def set_expected_value(self, expected_value_string, eval_expected_value):
        if not isinstance(expected_value_string, str):
            raise ActionError("Only string allowed as expected_value.", action=self)
        try:
            if eval_expected_value:
                self.expected_value = literal_eval("".join(expected_value_string.split('\\')))
            else:
                self.expected_value = expected_value_string
        except (ValueError, SyntaxError) as e:
            raise ActionError(f"Could not parse '{expected_value_string}'. {e}", action=self) from e

    def shutdown(self):
        if self.topic is not None:
            try:
                self.topic.unsubscribe()
            except Exception:  # pylint: disable=broad-except
                pass
