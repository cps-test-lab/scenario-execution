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
import tempfile
import unittest

from scenario_execution.utils.logging import BaseLogger
from scenario_execution_ros.actions.ros_bag_record import (RosBagRecord,
                                                           RosBagRecordActionState)


class RecordingLogger(BaseLogger):
    """A logger that keeps what it was told, by level, so a test can read it."""

    def __init__(self):
        super().__init__('test', False)
        self.errors = []
        self.other = []

    def info(self, msg):
        self.other.append(msg)

    def debug(self, msg):
        self.other.append(msg)

    def warning(self, msg):
        self.other.append(msg)

    def error(self, msg):
        self.errors.append(msg)


class TestRosBagRecordUnclosed(unittest.TestCase):
    """A recording the recorder never closed is reported, not left to its reader to discover."""
    # pylint: disable=missing-function-docstring, protected-access

    def _action(self, bag_dir):
        action = RosBagRecord()
        action._set_base_properities('bag_record', None, RecordingLogger())
        action.bag_dir = bag_dir
        action.current_state = RosBagRecordActionState.RECORDING
        return action

    def test_a_bag_without_its_sidecar_is_reported(self):
        # What a recorder that ignored SIGINT leaves behind: the data file is there and looks
        # like a recording, but rosbag2_storage cannot open the directory without the sidecar.
        # Silence here is what let a whole campaign of unreadable bags pass as successful runs.
        with tempfile.TemporaryDirectory() as bag_dir:
            with open(os.path.join(bag_dir, 'rosbag2_0.mcap'), 'wb') as data:
                data.write(b'not a real recording')
            action = self._action(bag_dir)
            action.report_unclosed_bag()
            self.assertEqual(len(action.logger.errors), 1, action.logger.errors)
            self.assertIn('metadata.yaml', action.logger.errors[0])
            self.assertIn(bag_dir, action.logger.errors[0])

    def test_a_closed_bag_says_nothing(self):
        with tempfile.TemporaryDirectory() as bag_dir:
            with open(os.path.join(bag_dir, RosBagRecord.BAG_METADATA), 'w', encoding='utf-8') as meta:
                meta.write('version: 9\n')
            action = self._action(bag_dir)
            action.report_unclosed_bag()
            self.assertEqual(action.logger.errors, [])

    def test_a_bag_discarded_for_want_of_topics_is_not_reported_as_lost(self):
        # A shutdown while the recorder is still waiting for its topics removes that bag on
        # purpose. It has no sidecar either, and calling that a lost recording would put an
        # error in the log of every scenario that ends before its topics appear.
        with tempfile.TemporaryDirectory() as root:
            bag_dir = os.path.join(root, 'rosbag2')
            os.mkdir(bag_dir)
            action = self._action(bag_dir)
            action.current_state = RosBagRecordActionState.WAITING_FOR_TOPICS
            action.process = None
            action.shutdown()
            self.assertEqual(action.logger.errors, [])
            self.assertFalse(os.path.isdir(bag_dir), "the incomplete bag was kept")

    def test_a_recording_that_never_started_is_not_reported_as_lost(self):
        # No directory at all is the case the existing teardown already handles: a shutdown
        # while still waiting for topics removes the incomplete bag. Reporting it as an
        # unreadable recording would turn that ordinary path into an error in every log.
        action = self._action(os.path.join(tempfile.gettempdir(), 'no-such-bag-dir'))
        action.report_unclosed_bag()
        self.assertEqual(action.logger.errors, [])
