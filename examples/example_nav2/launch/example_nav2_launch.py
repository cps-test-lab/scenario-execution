# Copyright (C) 2024 Intel Corporation
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

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution, LaunchConfiguration


def loopback_simulation_launch_file(nav2_bringup_dir):
    """nav2_bringup's TurtleBot 4 loopback simulation: navigation2 renamed it after Jazzy."""
    for name in ('tb4_loopback_simulation_launch.py', 'tb4_loopback_simulation.launch.py'):
        path = os.path.join(nav2_bringup_dir, 'launch', name)
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(f"nav2_bringup has no TurtleBot 4 loopback simulation in {nav2_bringup_dir}")


def generate_launch_description():

    example_nav2_dir = get_package_share_directory('example_nav2')
    nav2_bringup_dir = get_package_share_directory('nav2_bringup')
    scenario_execution_ros_dir = get_package_share_directory('scenario_execution_ros')

    scenario = LaunchConfiguration('scenario')
    use_sim_time = LaunchConfiguration('use_sim_time')

    return LaunchDescription([
        DeclareLaunchArgument('scenario', description='Scenario file to execute', default_value=PathJoinSubstitution([example_nav2_dir, 'scenarios', 'example_nav2.osc'])),
        DeclareLaunchArgument('use_sim_time', default_value='False',
                              description='Tick the tree and measure the scenario durations on /clock instead of host time'),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(loopback_simulation_launch_file(nav2_bringup_dir))
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([PathJoinSubstitution([scenario_execution_ros_dir, 'launch', 'scenario_launch.py'])]),
            launch_arguments={'scenario': scenario, 'use_sim_time': use_sim_time}.items()
        )
    ])
