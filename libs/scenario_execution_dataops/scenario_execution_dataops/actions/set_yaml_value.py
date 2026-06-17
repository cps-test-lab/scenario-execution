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

    def convert_value(self, value, value_type): # pylint: disable=too-many-return-statements
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

    def update(self) -> py_trees.common.Status:  # pylint: disable=too-many-return-statements
        path = Path(self.file_path)
        if not path.is_file():
            self.feedback_message = f"File not found: '{self.file_path}'"  # pylint: disable=attribute-defined-outside-init
            return py_trees.common.Status.FAILURE

        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            self.feedback_message = f"Failed to parse YAML file '{self.file_path}': {e}"  # pylint: disable=attribute-defined-outside-init
            return py_trees.common.Status.FAILURE

        keys = parse_yaml_path(self.key_path)

        # Navigate to the target location
        current = data
        for i, key in enumerate(keys[:-1]):
            if isinstance(key, int):
                try:
                    current = current[key]
                except (IndexError, TypeError) as e:
                    self.feedback_message = f"Array index {key} out of range at '{'.'.join(str(k) for k in keys[:i+1])}': {e}"  # pylint: disable=attribute-defined-outside-init
                    return py_trees.common.Status.FAILURE
            else:
                if key not in current:
                    if self.create_missing:
                        current[key] = {}
                    else:
                        self.feedback_message = f"Key '{key}' not found at '{'.'.join(str(k) for k in keys[:i+1])}' in '{self.file_path}' (create_missing=False)"  # pylint: disable=attribute-defined-outside-init
                        return py_trees.common.Status.FAILURE
                current = current[key]

        final_key = keys[-1]
        if not self.create_missing and final_key not in current:
            self.feedback_message = f"Key '{final_key}' not found at '{self.key_path}' in '{self.file_path}' (create_missing=False)"  # pylint: disable=attribute-defined-outside-init
            return py_trees.common.Status.FAILURE

        try:
            converted_value = self.convert_value(self.value, self.value_type)
        except (ValueError, TypeError) as e:
            self.feedback_message = f"Could not convert value {self.value!r} to {self.value_type}: {e}"  # pylint: disable=attribute-defined-outside-init
            return py_trees.common.Status.FAILURE

        current[final_key] = converted_value

        output = self.output_file if self.output_file else self.file_path
        try:
            with open(output, 'w') as f:
                yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        except OSError as e:
            self.feedback_message = f"Failed to write output file '{output}': {e}"  # pylint: disable=attribute-defined-outside-init
            return py_trees.common.Status.FAILURE

        return py_trees.common.Status.SUCCESS
