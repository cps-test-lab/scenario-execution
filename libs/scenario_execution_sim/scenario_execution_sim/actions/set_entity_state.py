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

class SetEntityState(RosServiceCall):

    def __init__(self, entity: str, state: str):
        self.entity = entity
        self.state = state
        super().__init__(service_name='/simulation/set_entity_state',
                         service_type='simulation_interfaces.srv.SetEntityState')

    def execute(self):   # pylint: disable=arguments-differ,arguments-renamed
        super().execute(data=f'{{ "entity": "{self.entity}", "state": {self.state} }}')

    def check_response(self, msg):
        """
        Check if the response is valid.
        """
        if not msg.result.result == Result.RESULT_OK:
            self.feedback_message = f"Failed to set entity state for {self.entity}: result {msg.result.result}, error_message {msg.result.error_message}"
            return False
        self.feedback_message = f"Set entity state for {self.entity} successfully"
        return True
