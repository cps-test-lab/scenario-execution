# Copyright (C) 2026 Frederik Pasch
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

import unittest
from unittest.mock import ANY, Mock, patch

from antlr4.InputStream import InputStream
import py_trees

from scenario_execution.get_osc_library import (
    get_helpers_library,
    get_robotics_library,
    get_standard_library,
    get_types_library,
)
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.utils.logging import Logger
from scenario_execution_ros.actions.tf_close_to import TfCloseTo
from scenario_execution_ros.get_osc_library import get_ros_library
from scenario_execution_ros.marker_handler import MarkerHandler


class PublisherStub:

    def __init__(self):
        self.messages = []

    def publish(self, msg):
        self.messages.append(msg)


class EntryPointStub:

    def __init__(self, name, load_value, module_name="test"):
        self.name = name
        self.load_value = load_value
        self.module_name = module_name

    def load(self):
        return self.load_value


class NodeStub:

    def __init__(self):
        self.publisher = PublisherStub()

    def create_publisher(self, *_args, **_kwargs):
        return self.publisher


class TestTfCloseTo(unittest.TestCase):

    def entry_points(self, group):
        if group == "scenario_execution.osc_libraries":
            return [
                EntryPointStub("helpers", get_helpers_library),
                EntryPointStub("robotics", get_robotics_library),
                EntryPointStub("ros", get_ros_library),
                EntryPointStub("standard", get_standard_library),
                EntryPointStub("types", get_types_library),
            ]
        if group == "scenario_execution.actions":
            return [
                EntryPointStub(
                    "differential_drive_robot.tf_close_to",
                    TfCloseTo,
                    "scenario_execution_ros.actions.tf_close_to",
                )
            ]
        return []

    def build_action(self, scenario_content):
        parser = OpenScenario2Parser(Logger("test", False))
        tree = py_trees.composites.Sequence(name="", memory=True)
        parsed_tree = parser.parse_input_stream(InputStream(scenario_content))
        with patch(
            "scenario_execution.model.model_builder.entry_points",
            self.entry_points,
        ):
            model = parser.create_internal_model(parsed_tree, tree, "test.osc", False)
        with patch(
            "scenario_execution.model.model_to_py_tree.entry_points",
            self.entry_points,
        ):
            tree = create_py_tree(model, tree, parser.logger, False)

        for node in tree.iterate():
            if isinstance(node, TfCloseTo):
                return node
        raise AssertionError("TfCloseTo action not found in parsed scenario")

    def test_defaults_to_map_parent_frame(self):
        scenario_content = (
            "import osc.ros\n"
            "scenario test_tf_close_to_default_parent_frame:\n"
            "    robot: differential_drive_robot\n"
            "    do serial:\n"
            "        robot.tf_close_to(\n"
            "            reference_point: position_3d(x: 1.0m, y: 2.0m),\n"
            "            threshold: 0.4m)\n"
        )

        action = self.build_action(scenario_content)

        self.assertEqual("map", action.parent_frame_id)
        self.assertEqual("base_link", action.robot_frame_id)

    def test_uses_custom_parent_frame_for_lookup_and_marker(self):
        node = NodeStub()
        marker_handler = MarkerHandler(node)
        action = TfCloseTo(
            associated_actor={"namespace": ""},
            namespace_override="",
            reference_point={"x": 1.0, "y": 2.0},
            threshold=0.4,
            sim=False,
            robot_frame_id="base_link",
            parent_frame_id="odom",
        )

        with patch("scenario_execution_ros.actions.tf_close_to.Buffer"):
            with patch(
                "scenario_execution_ros.actions.tf_close_to.NamespacedTransformListener"
            ):
                action.setup(node=node, marker_handler=marker_handler)

        marker = marker_handler.get_marker(action.marker_id)
        self.assertEqual("odom", marker.header.frame_id)

        transform = Mock()
        transform.transform.translation = Mock()
        action.tf_buffer = Mock()
        action.tf_buffer.lookup_transform.return_value = transform
        action.node = Mock()

        translation, success = action.get_translation_from_tf()

        self.assertTrue(success)
        self.assertIs(translation, transform.transform.translation)
        action.tf_buffer.lookup_transform.assert_called_once_with("odom", "base_link", ANY)

    def test_parses_custom_parent_frame_argument(self):
        scenario_content = (
            "import osc.ros\n"
            "scenario test_tf_close_to_custom_parent_frame:\n"
            "    robot: differential_drive_robot\n"
            "    do serial:\n"
            "        robot.tf_close_to(\n"
            "            reference_point: position_3d(x: 1.0m, y: 2.0m),\n"
            "            parent_frame_id: 'odom',\n"
            "            threshold: 0.4m)\n"
        )

        action = self.build_action(scenario_content)

        self.assertEqual("odom", action.parent_frame_id)


if __name__ == "__main__":
    unittest.main()
