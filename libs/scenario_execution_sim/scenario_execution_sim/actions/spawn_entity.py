# Copyright (C) 2025 Frederik Pasch
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

from .common import get_spawn_pose
from scenario_execution_ros.actions.ros_service_call import RosServiceCall
try:
    from simulation_interfaces.msg import Result
except ImportError as e:
    raise ImportError("simulation_interfaces package not found. Please make sure ros-<ROS_DISTRO>-simulation-interfaces is installed and sourced.") from e

class SpawnEntity(RosServiceCall):

    def __init__(self, entity_name: str, allow_renaming: bool, uri: str, entity_namespace: str, initial_pose: dict):
        self.entity_name = entity_name
        self.allow_renaming = allow_renaming
        self.uri = uri
        self.entity_namespace = entity_namespace
        self.initial_pose = initial_pose
        super().__init__(service_name='/spawn_entity',
                         service_type='simulation_interfaces.srv.SpawnEntity')

    def execute(self):   # pylint: disable=arguments-differ,arguments-renamed
        data = {
            "name": self.entity_name,
            "allow_renaming": self.allow_renaming,
            "uri": self.uri,
            "entity_namespace": self.entity_namespace,
            "initial_pose": { 
                "pose": get_spawn_pose(self, self.initial_pose)
            }
        }
        super().execute(data)

    def check_response(self, msg):
        """
        Check if the response is valid.
        """
        if not msg.result.result == Result.RESULT_OK:
            return False, msg.result.error_message
        feedback_msg = msg.result.error_message
        if not feedback_msg:
            if hasattr(msg, "entity_name") and msg.entity_name:
                feedback_msg = f"Entity '{msg.entity_name}' spawned successfully."
            else:
                feedback_msg = f"Entity '{self.entity_name}' spawned successfully."
        return True, feedback_msg
