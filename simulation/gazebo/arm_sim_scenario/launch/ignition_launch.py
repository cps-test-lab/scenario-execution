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
from launch.actions import DeclareLaunchArgument, SetEnvironmentVariable, Shutdown, ExecuteProcess
from launch.substitutions import LaunchConfiguration, EnvironmentVariable
from launch_ros.actions import Node

# Define Launch Arguments
ARGUMENTS = [
    DeclareLaunchArgument(
        'world',
        default_value="empty.sdf",
        description='Simulation World File'
    )
]


def generate_launch_description():

    world = LaunchConfiguration('world')

    # Set environment variables
    ign_gazebo_resource_path = SetEnvironmentVariable(
        name='IGN_GAZEBO_RESOURCE_PATH',
        value=[
            EnvironmentVariable('IGN_GAZEBO_RESOURCE_PATH', default_value=os.path.dirname(
                get_package_share_directory('moveit_resources_panda_description')))
        ]
    )

    env = {
        'GZ_SIM_SYSTEM_PLUGIN_PATH': ':'.join([
            os.environ.get('GZ_SIM_SYSTEM_PLUGIN_PATH', ''),
            os.environ.get('LD_LIBRARY_PATH', '')
        ]),
    }

    # Ignition Gazebo Launch
    ignition_gazebo = ExecuteProcess(
        cmd=['gz', 'sim', world, '-r', '-v', '4'],
        output='screen',
        additional_env=env,
        on_exit=Shutdown(),
        sigterm_timeout='5',
        sigkill_timeout='10',
        log_cmd=True,
        emulate_tty=True
    )

    # Spawn Robot Node
    spawn_robot_node = Node(
        package="ros_gz_sim",
        executable="create",
        output="screen",
        arguments=[
            "-topic", "robot_description",
            "-name", "arm",
            "-allow-renaming", "true",
        ],
    )

    # Clock Bridge Node
    clock_bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=["/clock@rosgraph_msgs/msg/Clock[ignition.msgs.Clock"],
        output="screen",
    )

    # Create and Return Launch Description
    ld = LaunchDescription(ARGUMENTS)
    ld.add_action(ign_gazebo_resource_path)
    ld.add_action(ignition_gazebo)
    ld.add_action(clock_bridge)
    ld.add_action(spawn_robot_node)

    return ld
