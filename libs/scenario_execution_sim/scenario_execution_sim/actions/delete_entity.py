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


class DeleteEntity(RosServiceCall):

    def __init__(self, entity: str):
        self.entity = entity
        super().__init__(service_name='/simulation/delete_entity', 
                         service_type='simulation_interfaces.srv.DeleteEntity')

    def execute(self):   # pylint: disable=arguments-differ,arguments-renamed
        super().execute(data='{ "entity": "' + self.entity + '" }')
