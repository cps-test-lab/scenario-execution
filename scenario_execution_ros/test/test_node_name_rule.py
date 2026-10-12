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

"""One rule for naming a node, shared by wait_for_nodes, wait_for_service_server and
wait_for_topic_subscription."""

import unittest

from scenario_execution_ros.actions.conversions import node_name_matches


class TestNodeNameRule(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def test_a_bare_name_matches_that_node_in_any_namespace(self):
        self.assertTrue(node_name_matches("controller_server", "controller_server", "/"))
        self.assertTrue(node_name_matches("controller_server", "controller_server", "/robot1"))

    def test_a_qualified_name_matches_exactly(self):
        self.assertTrue(node_name_matches("/controller_server", "controller_server", "/"))
        self.assertTrue(node_name_matches("/robot1/controller_server", "controller_server", "/robot1"))
        self.assertFalse(node_name_matches("/controller_server", "controller_server", "/robot1"))
        self.assertFalse(node_name_matches("/robot1/controller_server", "controller_server", "/robot2"))

    def test_another_name_does_not_match(self):
        self.assertFalse(node_name_matches("planner_server", "controller_server", "/"))
