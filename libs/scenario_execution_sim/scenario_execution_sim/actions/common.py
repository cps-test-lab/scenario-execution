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

import math
from scenario_execution.actions.base_action import ActionError

def euler2quat(roll, pitch, yaw):
    """
    Convert Euler angles (roll, pitch, yaw) to quaternion (w, x, y, z).
    The input angles are in radians.
    The output quaternion is normalized.
    """

    cy = math.cos(yaw * 0.5)
    sy = math.sin(yaw * 0.5)
    cr = math.cos(roll * 0.5)
    sr = math.sin(roll * 0.5)
    cp = math.cos(pitch * 0.5)
    sp = math.sin(pitch * 0.5)

    w = cy * cr * cp + sy * sr * sp
    x = cy * sr * cp - sy * cr * sp
    y = cy * cr * sp + sy * sr * cp
    z = sy * cr * cp - cy * sr * sp

    return (x, y, z, w)

def get_spawn_pose(action, pose):
    try:
        quaternion = euler2quat(pose["orientation"]["roll"],
                                pose["orientation"]["pitch"],
                                pose["orientation"]["yaw"])
        pose = {
            "position": {
                    "x": pose["position"]["x"],
                    "y": pose["position"]["y"],
                    "z": pose["position"]["z"]
            },
            "orientation": {  
                    "x": quaternion[0],
                    "y": quaternion[1],
                    "z": quaternion[2],
                    "w": quaternion[3]
            }}
    except KeyError as e:
        raise ActionError("Could not get values", action=action) from e
    return pose
