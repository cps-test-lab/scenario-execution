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

from enum import Enum
from scenario_execution.actions.base_action import BaseAction
import py_trees
from concurrent.futures import ThreadPoolExecutor
import requests

class RequestStatus(Enum):
    IDLE = 1
    REQUESTING = 2
    DONE = 3


class HttpGet(BaseAction):
    """
    Class to perform an HTTP GET request asynchronously
    """

    def __init__(self) -> None:
        super().__init__()
        self.response = None
        self.future = None
        self.parameters = {}
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.current_state = RequestStatus.IDLE

    def execute(self, url: str, parameters: list) -> None:  # pylint: disable=arguments-differ,arguments-renamed
        self.url = url
        self.parameters = {}
        for param in parameters:
            self.parameters[param["key"]] = param["value"]

    def update(self) -> py_trees.common.Status:
        if self.current_state == RequestStatus.IDLE:
            # Start the async HTTP request in a separate thread
            self.future = self.executor.submit(self._make_request)
            self.current_state = RequestStatus.REQUESTING
            return py_trees.common.Status.RUNNING

        elif self.current_state == RequestStatus.REQUESTING:
            if self.future.done():
                try:
                    self.response = self.future.result()
                    if self.response.status_code == 200:
                        self.current_state = RequestStatus.DONE
                        return py_trees.common.Status.SUCCESS
                    else:
                        self.logger.error(f"HTTP GET returned status code {self.response.status_code}")
                        self.current_state = RequestStatus.DONE
                        return py_trees.common.Status.FAILURE
                except Exception as e:
                    self.logger.error(f"HTTP GET request failed: {e}")
                    return py_trees.common.Status.FAILURE
            else:
                return py_trees.common.Status.RUNNING

        elif self.current_state == RequestStatus.DONE:
            return py_trees.common.Status.SUCCESS

        return py_trees.common.Status.FAILURE

    def _make_request(self):
        """Make the HTTP request synchronously in a thread pool"""
        return requests.get(self.url, params=self.parameters)

    def shutdown(self):
        """Clean up the thread pool on shutdown"""
        if self.executor:
            self.executor.shutdown(wait=False)