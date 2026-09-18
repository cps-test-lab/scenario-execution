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

from glob import glob
import os
import re
from pathlib import Path
from setuptools import find_packages, setup

PACKAGE_NAME = 'scenario_execution_coverage'

# The version lives in package.xml alone: the ROS tooling reads it there and nowhere else,
# so a release bumps one file per package and this can never disagree with it.
VERSION = re.search(r"<version>\s*([^<\s]+)\s*</version>",
                    (Path(__file__).resolve().parent / "package.xml").read_text(encoding="utf-8")).group(1)

setup(
    name=PACKAGE_NAME,
    version=VERSION,
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + PACKAGE_NAME]),
        ('share/' + PACKAGE_NAME, ['package.xml']),
        (os.path.join('share', PACKAGE_NAME, 'launch'), glob('launch/*launch.py'))
    ],
    install_requires=[
        'setuptools',
        'pexpect==4.9',
        'defusedxml==0.7.1',
    ],
    zip_safe=True,
    maintainer='Frederik Pasch',
    maintainer_email='fred-labs@mailbox.org',
    description='Robotics Scenario Execution Coverage',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'scenario_variation = scenario_execution_coverage.scenario_variation:main',
            'scenario_batch_execution = scenario_execution_coverage.scenario_batch_execution:main',
        ],
    },
)
