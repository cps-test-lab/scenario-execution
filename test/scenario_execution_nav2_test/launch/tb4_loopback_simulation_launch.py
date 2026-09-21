# Copyright (C) 2026 Frederik Pasch
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

"""nav2_bringup's TurtleBot 4 loopback simulation, under the name it has on the installed distro.

A scenario names a launch file literally, and navigation2 renamed this one between Jazzy and
Lyrical. Launch arguments given here (``map``, ...) reach the included file unchanged.
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

NAMES = ('tb4_loopback_simulation_launch.py', 'tb4_loopback_simulation.launch.py')


def loopback_simulation_launch_file():
    launch_dir = os.path.join(get_package_share_directory('nav2_bringup'), 'launch')
    for name in NAMES:
        path = os.path.join(launch_dir, name)
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(f"nav2_bringup has none of {', '.join(NAMES)} in {launch_dir}")


def generate_launch_description():
    return LaunchDescription([
        IncludeLaunchDescription(PythonLaunchDescriptionSource(loopback_simulation_launch_file())),
    ])
