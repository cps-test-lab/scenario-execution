# Copyright (C) 2026 Frederik Pasch
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

import py_trees

from scenario_execution.actions.base_action import BaseAction, ActionError


class ProcessLogCheck(BaseAction):
    """
    Class for scanning the captured output of a process started by run_process.
    """

    def __init__(self):
        super().__init__()
        self.process_registry = None
        self.process_name = None
        self.values = None
        self.from_start = True
        self.process = None
        self.start_index = 0
        self.found = None

    def setup(self, **kwargs):
        try:
            self.process_registry = kwargs['process_registry']
        except KeyError as e:
            error_message = "didn't find 'process_registry' in setup's kwargs [{}][{}]".format(
                self.name, self.__class__.__name__)
            raise ActionError(error_message, action=self) from e
        self.feedback_message = "Waiting for process log"  # pylint: disable= attribute-defined-outside-init

    def execute(self, process_name: str, values: list, from_start: bool = True):
        self.process_name = process_name
        self.values = values
        self.from_start = from_start
        self.process = None
        self.start_index = 0
        self.found = None

    def update(self) -> py_trees.common.Status:
        """
        Wait for specified output in a run_process action.

        return:
            py_trees.common.Status if found
        """
        if self.found is None:
            self.found = False
            if not self._resolve_process():
                return py_trees.common.Status.FAILURE
            if not self.from_start:
                self.start_index = len(self.process.get_output_snapshot())

        output = self.process.get_output_snapshot()
        for line in output[self.start_index:]:
            for val in self.values:
                if val in line:
                    self.feedback_message = f"Found string '{val}' in '{line}'"  # pylint: disable= attribute-defined-outside-init
                    self.found = True
                    return py_trees.common.Status.SUCCESS

        if self.process.is_output_complete():
            self.feedback_message = f"No matching output found for process '{self.process_name}'"  # pylint: disable= attribute-defined-outside-init
            return py_trees.common.Status.FAILURE

        return py_trees.common.Status.RUNNING

    def _resolve_process(self):
        processes = self.process_registry.get(self.process_name)
        if not processes:
            self.feedback_message = f"No run_process action named '{self.process_name}' found"  # pylint: disable= attribute-defined-outside-init
            self.logger.error(self.feedback_message)
            return False

        if len(processes) > 1:
            self.feedback_message = (  # pylint: disable= attribute-defined-outside-init
                f"Process name '{self.process_name}' is ambiguous; use a unique run_process label")
            self.logger.error(self.feedback_message)
            return False

        self.process = processes[0]
        return True
