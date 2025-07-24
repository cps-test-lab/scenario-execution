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
import py_trees
import re
import psutil
from scenario_execution.actions.base_action import BaseAction


class CheckProcessRunning(BaseAction):
    """
    Check if a process is running
    """

    def __init__(self, process_name, regex=False):
        super().__init__()
        self.process_name = process_name
        self.regex = regex

    def update(self) -> py_trees.common.Status:
        if self.is_process_running(self.process_name):
            self.feedback_message = f"Process '{self.process_name}' is running"  # pylint: disable= attribute-defined-outside-init
            return py_trees.common.Status.SUCCESS
        else:
            self.feedback_message = f"Process '{self.process_name}' is not running"  # pylint: disable= attribute-defined-outside-init
            return py_trees.common.Status.FAILURE

    def is_process_running(self, process_name):
        """
        Check if a process with the given name is running, using psutil.

        If regex is True, process_name is treated as a regular expression and
        matched against process name and command line.

        Args:
            process_name (str): The name or regex of the process to check.

        Returns:
            bool: True if the process is running, False otherwise.
        """
        try:
            pattern = re.compile(process_name) if self.regex else None
            for proc in psutil.process_iter(['name', 'cmdline']):
                try:
                    name = proc.info.get('name') or ''
                    cmdline_list = proc.info.get('cmdline') or []
                    cmdline = ' '.join(cmdline_list)
                    target = f"{name} {cmdline}".strip()
                    if self.regex:
                        if pattern.search(target):
                            return True
                    else:
                        if process_name in name or process_name in cmdline:
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return False
        except Exception as e:
            self.feedback_message = f"Error checking process: {e}"
            return False