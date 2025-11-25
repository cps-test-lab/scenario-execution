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
try:
    from simulation_interfaces.msg import Result
except ImportError as e:
    raise ImportError("simulation_interfaces package not found. Please make sure ros-<ROS_DISTRO>-simulation-interfaces is installed and sourced.") from e

class ResetSimulation(RosServiceCall):

    def __init__(self):
        super().__init__(service_name='/reset_simulation',
                         service_type='simulation_interfaces.srv.ResetSimulation')

    def execute(self):   # pylint: disable=arguments-differ,arguments-renamed
        super().execute(data={})

    def check_response(self, msg):
        """
        Check if the response is valid.
        """
        if not msg.result.result == Result.RESULT_OK:
            return False, msg.result.error_message
        return True, msg.result.error_message
