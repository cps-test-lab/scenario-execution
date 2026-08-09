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

from setuptools import find_namespace_packages, setup

PACKAGE_NAME = 'scenario_execution_websocket'

setup(
    name=PACKAGE_NAME,
    version='1.5.0',
    packages=find_namespace_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + PACKAGE_NAME]),
        ('share/' + PACKAGE_NAME, ['package.xml'])
    ],
    install_requires=['setuptools', 'roslibpy'],
    zip_safe=True,
    maintainer='Frederik Pasch',
    maintainer_email='fred-labs@mailbox.org',
    description='Scenario Execution library speaking the rosbridge protocol (ROS-free)',
    license='Apache License 2.0',
    tests_require=['pytest'],
    include_package_data=True,
    entry_points={
        'scenario_execution.actions': [
            'rosbridge_topic_publish = scenario_execution_websocket.actions.rosbridge_topic_publish:RosbridgeTopicPublish',
            'rosbridge_topic_monitor = scenario_execution_websocket.actions.rosbridge_topic_monitor:RosbridgeTopicMonitor',
            'rosbridge_wait_for_data = scenario_execution_websocket.actions.rosbridge_wait_for_data:RosbridgeWaitForData',
            'rosbridge_check_data = scenario_execution_websocket.actions.rosbridge_check_data:RosbridgeCheckData',
            'rosbridge_service_call = scenario_execution_websocket.actions.rosbridge_service_call:RosbridgeServiceCall',
            'rosbridge_action_call = scenario_execution_websocket.actions.rosbridge_action_call:RosbridgeActionCall',
            'rosbridge_wait_for_topics = scenario_execution_websocket.actions.rosbridge_wait_for_topics:RosbridgeWaitForTopics',
            'rosbridge_wait_for_services = scenario_execution_websocket.actions.rosbridge_wait_for_services:RosbridgeWaitForServices',
            'rosbridge_get_parameter = scenario_execution_websocket.actions.rosbridge_get_parameter:RosbridgeGetParameter',
            'rosbridge_set_parameter = scenario_execution_websocket.actions.rosbridge_set_parameter:RosbridgeSetParameter',
        ],
        'scenario_execution.osc_libraries': [
            'rosbridge = '
            'scenario_execution_websocket.get_osc_library:get_osc_library',
        ]
    },
)
