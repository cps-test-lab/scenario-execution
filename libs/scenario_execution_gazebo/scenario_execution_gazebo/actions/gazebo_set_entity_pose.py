# Copyright (c) 2026 Enway GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from typing import Optional

import py_trees
from scenario_execution.actions.base_action import ActionError
from scenario_execution.actions.run_process import RunProcess
from transforms3d.euler import euler2quat


class SetEntityPoseActionState(Enum):
    """States for executing an entity pose set in gazebo."""

    IDLE = 1
    WAITING_FOR_RESPONSE = 2
    DONE = 3
    FAILURE = 4


class SetEntityPose(RunProcess):
    """Class to set the pose of an entity in gazebo."""

    def __init__(self) -> None:
        super().__init__()
        self.entity_name: Optional[str] = None
        self.current_state = SetEntityPoseActionState.IDLE

    def execute(self, entity_name: str, pose: dict, world_name: str) -> None:  # pylint: disable=arguments-differ
        super().execute(wait_for_shutdown=True)
        self.entity_name = entity_name
        self.world_name = world_name

        pose_str = self.parse_pose(pose)
        self.set_command(
            [
                "gz",
                "service",
                "-s",
                "/world/" + self.world_name + "/set_pose",
                "--reqtype",
                "gz.msgs.Pose",
                "--reptype",
                "gz.msgs.Boolean",
                "--timeout",
                "2000",
                "--req",
                'name: "' + self.entity_name + '", ' + pose_str,
            ]
        )

    def parse_pose(self, pose: dict) -> str:
        try:
            quaternion = euler2quat(
                pose["orientation"]["pitch"],
                pose["orientation"]["roll"],
                pose["orientation"]["yaw"],
            )
            pose_str = (
                "position: {"
                f'x: {pose["position"]["x"]}, y: {pose["position"]["y"]}, z: {pose["position"]["z"]}'
                "}, orientation: {"
                f"w: {quaternion[0]}, x: {quaternion[1]}, y: {quaternion[2]}, z: {quaternion[3]}"
                "}"
            )
        except KeyError as e:
            raise ActionError("Could not get values", action=self) from e
        return pose_str

    def on_executed(self) -> None:
        """Hook when process gets executed."""
        self.feedback_message = (
            f"Waiting for entity '{self.entity_name}'"  # pylint: disable= attribute-defined-outside-init
        )
        self.current_state = SetEntityPoseActionState.WAITING_FOR_RESPONSE

    def on_process_finished(self, ret: int) -> py_trees.common.Status:
        """Check result of process."""
        if self.current_state == SetEntityPoseActionState.WAITING_FOR_RESPONSE:
            if ret == 0:
                while True:
                    try:
                        line = self.output.popleft()
                        line = line.lower()
                        if "error" in line or "timed out" in line:
                            self.feedback_message = f"Found error output while executing '{self.get_command()}'"  # pylint: disable= attribute-defined-outside-init
                            self.current_state = SetEntityPoseActionState.FAILURE
                            return py_trees.common.Status.FAILURE
                    except IndexError:
                        break
                self.feedback_message = f"Successfully set pose for entity '{self.entity_name}'"
                self.current_state = SetEntityPoseActionState.DONE
                return py_trees.common.Status.SUCCESS
            else:
                self.feedback_message = f"Setting pose of '{self.entity_name}' failed with {ret}"
                self.current_state = SetEntityPoseActionState.FAILURE
                return py_trees.common.Status.FAILURE
        else:
            return py_trees.common.Status.INVALID
