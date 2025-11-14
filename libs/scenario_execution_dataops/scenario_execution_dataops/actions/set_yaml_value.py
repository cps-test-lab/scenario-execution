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

import os
import yaml
import json
import py_trees
from pathlib import Path
from scenario_execution.actions.base_action import BaseAction


def parse_yaml_path(yaml_path: str) -> list:
    """
    Parse a dot-separated path into a list of keys.
    Supports array indices: "servers.0.port" -> ["servers", 0, "port"]
    """
    keys = []
    for part in yaml_path.split('.'):
        # Check if it's an array index
        if part.isdigit():
            keys.append(int(part))
        else:
            keys.append(part)
    return keys

class SetYamlValue(BaseAction):
    """
    Set value within yaml file
    """

    def __init__(self, file_path, output_file, key_path, value, value_type, create_missing=True):
        super().__init__()
        self.file_path = file_path
        self.output_file = output_file
        self.key_path = key_path
        self.value = value
        self.value_type = value_type
        self.create_missing = create_missing

    def convert_value(self, value, value_type):
        """
        Convert the value to the specified type.

        Args:
            value: The input value (typically a string)
            value_type: The target type ('str', 'int', 'float', 'bool', 'list', 'dict')

        Returns:
            The converted value
        """
        if value_type == 'str':
            return str(value)
        elif value_type == 'int':
            return int(value)
        elif value_type == 'float':
            return float(value)
        elif value_type == 'bool':
            # Handle various boolean representations
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ('true', '1', 'yes', 'on')
            return bool(value)
        elif value_type == 'list':
            # If already a list, return it
            if isinstance(value, list):
                return value
            # Try to parse as JSON/YAML
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, list):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    # Try YAML parsing
                    try:
                        parsed = yaml.safe_load(value)
                        if isinstance(parsed, list):
                            return parsed
                    except yaml.YAMLError:
                        pass
            raise ValueError(f"Cannot convert value to list: {value}")
        elif value_type == 'dict':
            # If already a dict, return it
            if isinstance(value, dict):
                return value
            # Try to parse as JSON/YAML
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    # Try YAML parsing
                    try:
                        parsed = yaml.safe_load(value)
                        if isinstance(parsed, dict):
                            return parsed
                    except yaml.YAMLError:
                        pass
            raise ValueError(f"Cannot convert value to dict: {value}")
        else:
            # If no type specified or unknown type, return as-is
            return value

    def update(self) -> py_trees.common.Status:
        result = True
        path = Path(self.file_path)
        if not path.is_file():
            result = False
        
        if result:
            # Load YAML
            with open(path, 'r') as f:
                data = yaml.safe_load(f) or {}
            
            # Parse the key_path
            keys = parse_yaml_path(self.key_path)
        
            # Navigate to the target location
            current = data
            for key in keys[:-1]:
                if isinstance(key, int):
                    # Array access
                    current = current[key]
                else:
                    # Dictionary access
                    if key not in current:
                        if self.create_missing:
                            current[key] = {}
                        else:
                            result = False
                            break
                    current = current[key]

        if result:
            # Perform the operation on the final key
            final_key = keys[-1]

            # Check if final key exists when create_missing is False
            if not self.create_missing and final_key not in current:
                result = False
            else:
                # Convert the value to the specified type
                try:
                    converted_value = self.convert_value(self.value, self.value_type)
                    current[final_key] = converted_value
                except (ValueError, TypeError) as e:
                    self.feedback_message = f"Could not convert value {self.value} to {self.value_type}: {e}"  # pylint: disable= attribute-defined-outside-init
                    result = False

        # Write back to file only if operation succeeded
        if result:
            if self.output_file:
                output = self.output_file
            else:
                output = self.file_path
            with open(output, 'w') as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            return py_trees.common.Status.SUCCESS
        else:
            return py_trees.common.Status.FAILURE
