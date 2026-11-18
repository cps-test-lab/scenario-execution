# Copyright (C) 2024 Intel Corporation
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

import py_trees
import yaml
from scenario_execution.model.types import ParameterDeclaration, ScenarioDeclaration, print_tree, deserialize
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.model_blackboard import create_py_tree_blackboard
from scenario_execution.model.model_resolver import resolve_internal_model


class ModelFileLoader(object):

    def __init__(self, logger) -> None:
        self.logger = logger

    def process_file(self, file_name, log_tree: bool = False, debug: bool = False, scenario_parameter_file: str = None,
                     create_scenario_parameter_file_template: bool = False):
        """Load a serialized model and build its scenario's tree.

        A serialized model is concrete, its parameters resolved when it was written, so a
        scenario parameter file or a template for one is refused rather than ignored.
        """
        if create_scenario_parameter_file_template:
            raise ValueError(f"A scenario parameter file template is created from an .osc scenario, not from '{file_name}'.")
        if scenario_parameter_file:
            raise ValueError(f"A scenario parameter file overrides an .osc scenario; '{file_name}' is a serialized "
                             f"model whose parameters are resolved, so '{scenario_parameter_file}' is refused.")
        model = self.load_file(file_name, log_tree)
        scenario = model.find_first_child_of_type(ScenarioDeclaration)
        if scenario is None:
            raise ValueError(f"No scenario defined in '{file_name}'.")
        tree = py_trees.composites.Sequence(name="", memory=True)
        resolve_internal_model(model, tree, self.logger, log_tree)
        create_py_tree_blackboard(model, tree, self.logger, debug)
        create_py_tree(model, tree, self.logger, log_tree)
        params = {
            parameter.name: parameter.get_resolved_value()
            for parameter in scenario.find_children_of_type(ParameterDeclaration)
        }
        return [(tree, params, None, {})]

    def load_file(self, file_name, log_tree):
        """Load a serialized internal model.

        Raises ValueError naming the file if it cannot be read or is not a serialized
        model, as OpenScenario2Parser.parse_file does for an unreadable .osc.
        """
        try:
            with open(file_name, 'rb') as input_file:
                serialize_data = yaml.safe_load(input_file)  # nosec B301 TODO
            model = deserialize(serialize_data)
        except Exception as e:  # pylint: disable=broad-except
            raise ValueError(f"Unable to load scenario model from '{file_name}': {e}") from e

        if log_tree:
            self.logger.info("----Internal model-----")
            print_tree(model, self.logger)
        return model
