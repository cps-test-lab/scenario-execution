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
    from simulation_interfaces.msg import Result, SimulationState
except ImportError as e:
    raise ImportError("simulation_interfaces package not found. Please make sure ros-<ROS_DISTRO>-simulation-interfaces is installed and sourced.") from e

class SetSimulationState(RosServiceCall):

    def __init__(self, state: tuple):
        if state[0] == 'stopped':
            self.state = SimulationState.STATE_STOPPED
        elif state[0] == 'playing':
            self.state = SimulationState.STATE_PLAYING
        elif state[0] == 'paused':
            self.state = SimulationState.STATE_PAUSED
        else:
            raise ValueError(f"Invalid simulation state: {state[0]}")
        super().__init__(service_name='/set_simulation_state',
                         service_type='simulation_interfaces.srv.SetSimulationState')

    def execute(self):   # pylint: disable=arguments-differ,arguments-renamed
        super().execute(data={ "state": {"state": int(self.state)} })

    def check_response(self, msg):
        """
        Check if the response is valid.
        """
        if not msg.result.result == Result.RESULT_OK:
            return False, msg.result.error_message
        if self.state == SimulationState.STATE_PLAYING:
            feedback_message = "Simulation started playing."
        elif self.state == SimulationState.STATE_PAUSED:
            feedback_message = "Simulation paused."
        elif self.state == SimulationState.STATE_STOPPED:
            feedback_message = "Simulation stopped."
        else:
            feedback_message = f"Simulation state changed: {self.state}"
        return True, feedback_message
