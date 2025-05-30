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

def get_robotics_library():
    return 'scenario_execution', 'robotics.osc'


def get_helpers_library():
    return 'scenario_execution', 'helpers.osc'


def get_standard_library():
    return 'scenario_execution', 'standard.osc'


def get_types_library():
    return 'scenario_execution', 'types.osc'
