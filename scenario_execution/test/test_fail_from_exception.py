# Copyright (C) 2026 Intel Corporation
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

import unittest

from scenario_execution import ScenarioExecution


class _RecordingLogger:
    """Logger that keeps what was written, so a test can assert on it."""

    def __init__(self):
        self.errors = []

    def error(self, msg):
        self.errors.append(msg)

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def debug(self, msg):
        pass


class TestFailFromException(unittest.TestCase):
    """
    A scenario that dies from an exception must record WHERE, not only WHAT.

    The recorded verdict carries `str(e)`, and for a whole class of errors that string names no
    location: `RecursionError` stringifies to "maximum recursion depth exceeded" and nothing more,
    so every run that dies that way yields an identical verdict and the only way left to narrow it
    is to re-run the scenario with parts removed. These tests pin the traceback to the log.
    """

    def setUp(self) -> None:
        self.scenario_execution = ScenarioExecution(debug=False,
                                                    log_model=False,
                                                    live_tree=False,
                                                    scenario_file='test',
                                                    output_dir='')
        self.logger = _RecordingLogger()
        self.scenario_execution.logger = self.logger
        self.shutdown_calls = []
        self.scenario_execution.on_scenario_shutdown = (
            lambda result, msg="", out="": self.shutdown_calls.append((result, msg, out)))

    def _raise_and_report(self, exc, message="Run failed"):
        try:
            raise exc
        except Exception as e:  # pylint: disable=broad-except
            self.scenario_execution.fail_from_exception(message, e)

    def test_traceback_reaches_the_log(self):
        self._raise_and_report(RecursionError("maximum recursion depth exceeded"))
        self.assertEqual(len(self.logger.errors), 1)
        logged = self.logger.errors[0]
        self.assertIn("RecursionError", logged)
        # The frame that raised is what the verdict cannot supply.
        self.assertIn("_raise_and_report", logged)
        self.assertIn("Traceback", logged)

    def test_verdict_is_unchanged(self):
        # The point of the change is an ADDITIONAL artifact; the recorded verdict must not move,
        # because results already in the corpus were graded against this exact shape.
        self._raise_and_report(ValueError("some failure"), message="Setup failed")
        self.assertEqual(self.shutdown_calls, [(False, "Setup failed", "some failure")])

    def test_failure_message_is_carried_into_the_log(self):
        # Four call sites share this helper and they fail for different reasons; the log has to say
        # which one, or it cannot be told from the others.
        self._raise_and_report(RuntimeError("boom"), message="Simulation reset failed")
        self.assertIn("Simulation reset failed", self.logger.errors[0])
