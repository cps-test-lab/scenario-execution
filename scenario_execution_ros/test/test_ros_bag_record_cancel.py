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

import os
import signal
import subprocess
import unittest

from scenario_execution.utils.logging import BaseLogger
from scenario_execution_ros.actions.ros_bag_record import RosBagRecord


class RecordingLogger(BaseLogger):
    """A logger that keeps what it was told, so a test can read it."""

    def __init__(self):
        super().__init__('test', False)
        self.messages = []

    def info(self, msg):
        self.messages.append(msg)

    def debug(self, msg):
        self.messages.append(msg)

    def warning(self, msg):
        self.messages.append(msg)

    def error(self, msg):
        self.messages.append(msg)


class TestRosBagRecordCancel(unittest.TestCase):
    """What a cancelled recording sends, and how long it waits before killing."""
    # pylint: disable=missing-function-docstring

    def test_a_cancel_sends_the_signal_that_closes_the_bag(self):
        # SIGINT and nothing else: ros2 bag flushes its cache and writes the bag's metadata on
        # SIGINT, so a cancel that sends SIGTERM leaves an unreadable recording behind -- and the
        # branch that is being abandoned is exactly the run whose evidence is worth keeping.
        action = RosBagRecord()
        self.assertEqual(action.shutdown_signal, signal.SIGINT)
        self.assertEqual(action.shutdown_timeout, RosBagRecord.SHUTDOWN_TIMEOUT)

    def test_a_cancel_stops_the_process_rather_than_raising(self):
        # The action builds its command in its own execute(), so the base class's stop defaults
        # are all it has. With none, the first cancel raised and the scenario died with it.
        action = RosBagRecord()
        action._set_base_properities('bag_record', None, RecordingLogger())  # pylint: disable=protected-access
        # `sleep` stands in for the recorder: what is tested is the signal the action sends, and a
        # real `ros2 bag record` would need topics, a writable bag dir and a running graph.
        action.process = subprocess.Popen(['sleep', '30'], start_new_session=True)
        self.addCleanup(self._kill, action.process)

        self.assertTrue(action.request_cancel())

        action.process.wait(10)
        self.assertEqual(action.process.returncode, -signal.SIGINT)

    @staticmethod
    def _kill(process):
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
