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

import importlib
import threading
import unittest
from types import SimpleNamespace

import py_trees
import rclpy
from antlr4.InputStream import InputStream
from rclpy.action import ActionServer
from rclpy.callback_groups import ReentrantCallbackGroup
from nav2_msgs.action import FollowWaypoints

from scenario_execution_ros import ROSScenarioExecution
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.utils.logging import Logger
from scenario_execution_nav2.actions.follow_waypoints import describe_missed_waypoints

NAV2_ERROR_MSG = "Controller server is not active"


def missed_waypoint_entries(indices, error_code):
    """``missed_waypoints`` entries in the shape the installed nav2_msgs defines."""
    field_type = FollowWaypoints.Result.get_fields_and_field_types()['missed_waypoints']
    element_type = field_type[len('sequence<'):-1]
    if '/' not in element_type:
        return list(indices)
    package, name = element_type.split('/')
    msg_type = getattr(importlib.import_module(f'{package}.msg'), name)
    entries = []
    for index in indices:
        entry = msg_type()
        if hasattr(entry, 'waypoint_index'):
            entry.waypoint_index = index
        else:
            entry.index = index
        entry.error_code = error_code
        if hasattr(entry, 'error_msg'):
            entry.error_msg = NAV2_ERROR_MSG
        entries.append(entry)
    return entries


class TestDescribeMissedWaypoints(unittest.TestCase):
    """The failure message for each shape nav2_msgs has given ``missed_waypoints``."""
    # pylint: disable=missing-function-docstring

    def test_none_missed(self):
        self.assertIsNone(describe_missed_waypoints(SimpleNamespace(missed_waypoints=[])))

    def test_indices_only(self):
        self.assertEqual(describe_missed_waypoints(SimpleNamespace(missed_waypoints=[0, 3])),
                         "2 waypoint(s) missed: index 0, index 3")

    def test_missed_waypoint(self):
        result = SimpleNamespace(missed_waypoints=[SimpleNamespace(index=2, goal=None, error_code=104)])
        self.assertEqual(describe_missed_waypoints(result), "1 waypoint(s) missed: index 2 (error 104)")

    def test_waypoint_status(self):
        result = SimpleNamespace(missed_waypoints=[
            SimpleNamespace(waypoint_index=0, waypoint_status=3, error_code=104, error_msg="no valid path"),
            SimpleNamespace(waypoint_index=1, waypoint_status=3, error_code=0, error_msg="")])
        self.assertEqual(describe_missed_waypoints(result),
                         "2 waypoint(s) missed: index 0 (error 104: no valid path), index 1")


class TestFollowWaypoints(unittest.TestCase):
    """A goal nav2 succeeds with missed waypoints is not a scenario success."""
    # pylint: disable=missing-function-docstring

    def setUp(self):
        rclpy.init()
        self.node = rclpy.create_node('test_node_follow_waypoints')

        self.executor = rclpy.executors.MultiThreadedExecutor()
        self.executor.add_node(self.node)
        self.executor_thread = threading.Thread(target=self.executor.spin)
        self.executor_thread.start()

        self.parser = OpenScenario2Parser(Logger('test', False))
        self.scenario_execution_ros = ROSScenarioExecution()
        #: The waypoint indices the server reports as missed while succeeding the goal.
        self.missed_indices = []
        self.goal_poses_received = None

        self.action_server = ActionServer(
            self.node,
            FollowWaypoints,
            '/follow_waypoints',
            execute_callback=self.execute_callback,
            callback_group=ReentrantCallbackGroup())
        self.tree = py_trees.composites.Sequence(name="", memory=True)

    def tearDown(self):
        self.action_server.destroy()
        self.node.destroy_node()
        rclpy.try_shutdown()
        self.executor_thread.join()

    def execute(self, scenario_content):
        parsed_tree = self.parser.parse_input_stream(InputStream(scenario_content))
        model = self.parser.create_internal_model(parsed_tree, self.tree, "test.osc", False)
        self.tree = create_py_tree(model, self.tree, self.parser.logger, False)
        self.scenario_execution_ros.scenarios_list = [(self.tree, {}, None)]
        self.scenario_execution_ros.run()

    def execute_callback(self, goal_handle):
        """What nav2's waypoint follower does with ``stop_on_failure: false``: succeed regardless."""
        poses = goal_handle.request.poses
        self.goal_poses_received = len(getattr(poses, 'goals', poses))
        result = FollowWaypoints.Result()
        result.missed_waypoints = missed_waypoint_entries(self.missed_indices, 104)
        goal_handle.succeed()
        return result

    @staticmethod
    def scenario(parameters=""):
        return """
import osc.helpers
import osc.ros
import osc.nav2

scenario test:
    timeout(30s)
    robot: differential_drive_robot
    do serial:
        robot.follow_waypoints([pose_3d(position_3d(x: 1.0m)), pose_3d(position_3d(x: 2.0m)),
                                pose_3d(position_3d(x: 3.0m))]""" + parameters + """)
"""

    def test_all_waypoints_reached_succeeds(self):
        self.execute(self.scenario())
        self.assertEqual(self.goal_poses_received, 3)
        self.assertTrue(self.scenario_execution_ros.process_results())

    def test_missed_waypoints_fail(self):
        self.missed_indices = [0, 2]
        self.execute(self.scenario())
        self.assertEqual(self.goal_poses_received, 3)
        self.assertFalse(self.scenario_execution_ros.process_results())
        failure_output = self.scenario_execution_ros.results[0].failure_output
        self.assertIn("2 waypoint(s) missed", failure_output)
        self.assertIn("index 0", failure_output)
        self.assertIn("index 2", failure_output)

    def test_every_waypoint_missed_fails(self):
        self.missed_indices = [0, 1, 2]
        self.execute(self.scenario())
        self.assertFalse(self.scenario_execution_ros.process_results())
        self.assertIn("3 waypoint(s) missed", self.scenario_execution_ros.results[0].failure_output)

    def test_allow_missed_waypoints_succeeds(self):
        self.missed_indices = [1]
        self.execute(self.scenario(", allow_missed_waypoints: true"))
        self.assertTrue(self.scenario_execution_ros.process_results())
