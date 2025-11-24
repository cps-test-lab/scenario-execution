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

""" Setup python package """
from setuptools import find_namespace_packages, setup

PACKAGE_NAME = 'scenario_execution_sim'

setup(
    name=PACKAGE_NAME,
    version='1.3.0',
    packages=find_namespace_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + PACKAGE_NAME]),
        ('share/' + PACKAGE_NAME, ['package.xml'])
    ],
    install_requires=[
        'setuptools',
        'transforms3d==0.4.1',
        'defusedxml==0.7.1',
    ],
    zip_safe=True,
    maintainer='Frederik Pasch',
    maintainer_email='fred-labs@mailbox.org',
    description='Scenario Execution library for Simulations',
    license='Apache License 2.0',
    tests_require=['pytest'],
    include_package_data=True,
    entry_points={
        'scenario_execution.actions': [
            'delete_entity = scenario_execution_sim.actions.delete_entity:DeleteEntity',
            'load_world = scenario_execution_sim.actions.load_world:LoadWorld',
            'reset_simulation = scenario_execution_sim.actions.reset_simulation:ResetSimulation',
            # 'set_entity_info = scenario_execution_sim.actions.set_entity_info:SetEntityInfo',
            'set_entity_state = scenario_execution_sim.actions.set_entity_state:SetEntityState',
            'set_simulation_state = scenario_execution_sim.actions.set_simulation_state:SetSimulationState',
            'spawn_entity = scenario_execution_sim.actions.spawn_entity:SpawnEntity',
            'step_simulation = scenario_execution_sim.actions.step_simulation:StepSimulation',
            'unload_world = scenario_execution_sim.actions.unload_world:UnloadWorld',
        ],
        'scenario_execution.osc_libraries': [
            'sim = '
            'scenario_execution_sim.get_osc_library:get_sim_library',
        ]
    },
)
