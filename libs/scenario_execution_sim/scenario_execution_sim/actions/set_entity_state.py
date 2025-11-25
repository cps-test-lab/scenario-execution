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
from scenario_execution.actions.base_action import ActionError

try:
    from simulation_interfaces.msg import Result
except ImportError as e:
    raise ImportError("simulation_interfaces package not found. Please make sure ros-<ROS_DISTRO>-simulation-interfaces is installed and sourced.") from e

class SetEntityState(RosServiceCall):

    def __init__(self, entity: str, pose: dict, twist: dict, acceleration: dict):
        self.entity = entity
        self.pose = pose
        self.twist = twist
        self.acceleration = acceleration
        super().__init__(service_name='/set_entity_state',
                         service_type='simulation_interfaces.srv.SetEntityState')

    def convert_value(self, value: dict):
        try:
            result = {
                'linear': {
                    'x': value['translational']['x'],
                    'y': value['translational']['y'],
                    'z': value['translational']['z']
                },
                'angular': {
                    'x': value['angular']['roll'],
                    'y': value['angular']['pitch'],
                    'z': value['angular']['yaw']
                }
            }
        except KeyError as err:
            raise ActionError(f"Invalid value format: {self.twist}", action=self) from err
        return result

    def execute(self):   # pylint: disable=arguments-differ,arguments-renamed
        super().execute(data={ "entity": self.entity, "state": { "pose": get_spawn_pose(self, self.pose), "twist": self.convert_value(self.twist), "acceleration": self.convert_value(self.acceleration) }})

    def check_response(self, msg):
        """
        Check if the response is valid.
        """
        if not msg.result.result == Result.RESULT_OK:
            return False, msg.result.error_message
        return True, msg.result.error_message
