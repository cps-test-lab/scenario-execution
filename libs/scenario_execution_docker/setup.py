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

""" Setup python package """
from setuptools import find_namespace_packages, setup

PACKAGE_NAME = 'scenario_execution_docker'

setup(
    name=PACKAGE_NAME,
    version='1.3.0',
    packages=find_namespace_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + PACKAGE_NAME]),
        ('share/' + PACKAGE_NAME, ['package.xml'])
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Frederik Pasch',
    maintainer_email='fred-labs@mailbox.org',
    description='Scenario Execution library for Docker interactions',
    license='Apache License 2.0',
    tests_require=['pytest'],
    include_package_data=True,
    entry_points={
        'scenario_execution.actions': [
            'docker_run = scenario_execution_docker.actions.docker_run:DockerRun',
            'docker_exec = scenario_execution_docker.actions.docker_exec:DockerExec',
            'docker_copy = scenario_execution_docker.actions.docker_copy:DockerCopy',
            'docker_put = scenario_execution_docker.actions.docker_put:DockerPut',
        ],
        'scenario_execution.osc_libraries': [
            'docker = '
            'scenario_execution_docker.get_osc_library:get_osc_library',
        ]
    },
)
