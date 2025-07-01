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


from scenario_execution_ros.actions.ros_service_call import RosServiceCall
from simulation_interfaces.msg import Result

class SpawnEntity(RosServiceCall):

    def __init__(self, entity_name: str = "", allow_renaming: bool = True, uri: str = "", resource_string: str = "", entity_namespace: str = "", initial_pose: str = ""):
        self.entity_name = entity_name
        self.allow_renaming = allow_renaming
        self.uri = uri
        self.resource_string = resource_string
        self.entity_namespace = entity_namespace
        self.initial_pose = initial_pose
        super().__init__(service_name='/simulation/spawn_entity', 
                         service_type='simulation_interfaces.srv.SpawnEntity')

    def execute(self):   # pylint: disable=arguments-differ,arguments-renamed
        
        # TODO
        # data = {
        #     "name": self.entity_name,
        #     "allow_renaming": self.allow_renaming,
        #     "uri": self.uri,
        #     "resource_string": self.resource_string,
        #     "entity_namespace": self.entity_namespace,
        #     "initial_pose": {
        #         "pose": {
        #             "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        #             "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}
        #         }
        #     }
        # }
        # if self.initial_pose:
        #     data["initial_pose"] = self.initial_pose
        
        super().execute("{}")
    

    def check_response(self, msg):
        """
        Check if the response is valid.
        """
        # if not msg.result.result == Result.RESULT_OK:
        #     self.feedback_message = f"Failed to spawn entity: result {msg.result.result}, error_message {msg.result.error_message}"
        #     return False
        # self.feedback_message = f"Entity spawned successfully as {msg.result.entity_name}"
        return True
