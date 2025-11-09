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

"""
External interface for querying scenario information without full dependency resolution.

This module provides convenient functions for external Python applications to query
scenario properties before execution, without requiring all execution dependencies
to be loaded.
"""

import os
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.model_file_loader import ModelFileLoader
from scenario_execution.model.types import (
    ScenarioDeclaration,
    ParameterDeclaration,
    PhysicalTypeDeclaration,
    StructDeclaration,
)
from scenario_execution.utils.logging import Logger

def get_scenario_parameters(scenario_file: str, logger=None):
    """
    Extract scenario parameters from an OpenSCENARIO 2 file without resolving dependencies.
    
    This function parses the scenario file and loads the internal model to extract parameter
    information. It does not require external dependencies to be loaded, making it suitable
    for querying scenario parameters before full execution.
    
    Args:
        scenario_file: Path to the .osc or .sce scenario file
        logger: Optional logger instance. If None, a default logger will be created.
    
    Returns:
        A dictionary mapping scenario names to their parameters. Each parameter is represented
        as a dictionary containing:
        - 'name': parameter name
        - 'type': parameter type as string
        - 'is_list': boolean indicating if the parameter is a list
        
    Raises:
        ValueError: If the file does not exist, has unknown extension, or parsing fails
    
    Example:
        >>> params = get_scenario_parameters("my_scenario.osc")
        >>> print(params)
        {
            'my_scenario': [
                {'name': 'speed', 'type': 'speed', 'default_value': 5.0, 'is_list': False},
                {'name': 'waypoints', 'type': 'position', 'default_value': None, 'is_list': True}
            ]
        }
    """
    if logger is None:
        logger = Logger('get_scenario_parameters', False)
    
    # Check file exists
    if not os.path.isfile(scenario_file):
        raise ValueError(f"Scenario file does not exist: {scenario_file}")
    
    # Check file extension
    file_extension = os.path.splitext(scenario_file)[1]
    if file_extension == '.osc':
        parser = OpenScenario2Parser(logger)
    elif file_extension == '.sce':
        parser = ModelFileLoader(logger)
    else:
        raise ValueError(f"File has unknown extension '{file_extension}'. Allowed [.osc, .sce]")
    
    # Parse and load internal model (no dependency resolution)
    try:
        parsed_model = parser.parse_file(scenario_file, log_model=False)
        model = parser.load_internal_model(parsed_model, scenario_file, log_model=False, debug=False, skip_imports=True)
    except Exception as e:
        raise ValueError(f"Failed to parse scenario file: {e}") from e
    
    # Extract parameters from all scenarios
    result = {}
    scenarios = model.find_children_of_type(ScenarioDeclaration)
    
    if not scenarios:
        raise ValueError("No scenario definitions found in file")
    
    for scenario in scenarios:
        scenario_params = []
        parameters = scenario.find_children_of_type(ParameterDeclaration)
        
        for param in parameters:
            param_type, is_list = param.get_type()
            
            # Get type string
            if isinstance(param_type, str):
                type_str = param_type
            elif isinstance(param_type, PhysicalTypeDeclaration):
                type_str = param_type.name
            elif isinstance(param_type, StructDeclaration):
                type_str = param_type.name
            else:
                type_str = str(param_type)
            
            scenario_params.append({
                'name': param.name,
                'type': type_str,
                'is_list': is_list
            })
        
        result[scenario.name] = scenario_params
    
    return result
