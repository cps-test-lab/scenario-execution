# Copyright (C) 2026 Frederik Pasch
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
import signal
import subprocess  # nosec B404
import sys
import unittest

from scenario_execution.scenario_execution_base import ScenarioExecution


class TestSignalRegistration(unittest.TestCase):
    """Which signals the runner takes, and what its children inherit because of it."""
    # pylint: disable=missing-function-docstring

    def setUp(self):
        self.previous = {sig: signal.getsignal(sig)
                         for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT)}

    def tearDown(self):
        for sig, handler in self.previous.items():
            signal.signal(sig, handler)

    def _runner(self, register_signal=True):
        return ScenarioExecution(debug=False, log_model=False, live_tree=False,
                                 scenario_file='UNKNOWN_FILE.osc', output_dir="",
                                 register_signal=register_signal)

    def test_the_runner_takes_every_signal_that_asks_it_to_stop(self):
        self._runner()
        for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT):
            self.assertTrue(callable(signal.getsignal(sig)),
                            f"{signal.Signals(sig).name} has no handler")

    def test_an_inherited_ignore_is_replaced_rather_than_kept(self):
        # A runner started as a background job by a shell without job control arrives with
        # SIGINT ignored. Keeping that -- the usual courtesy to the launcher -- leaves the
        # runner uninterruptible AND hands the ignore to every process it spawns, including a
        # bag recorder that closes its recording on SIGINT and on nothing else.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self._runner()
        self.assertNotEqual(signal.getsignal(signal.SIGINT), signal.SIG_IGN)

    def test_register_signal_false_leaves_the_dispositions_alone(self):
        # An embedder that drives the runner itself keeps its own handlers.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self._runner(register_signal=False)
        self.assertEqual(signal.getsignal(signal.SIGINT), signal.SIG_IGN)

    @unittest.skipUnless(os.path.isdir('/proc/self'), "reads signal masks from /proc")
    def test_a_child_spawned_after_registration_can_be_interrupted(self):
        # The property the recorder depends on: exec resets a HANDLED signal to its default,
        # so taking SIGINT here is what gives every child a live one -- even when this process
        # inherited an ignore it cannot otherwise undo.
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        self._runner()
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])  # nosec B603
        self.addCleanup(self._reap, child)
        with open(f"/proc/{child.pid}/status", encoding="utf-8") as status:
            ignored = next(int(line.split()[1], 16)
                           for line in status if line.startswith("SigIgn:"))
        self.assertEqual(ignored & (1 << (signal.SIGINT - 1)), 0,
                         "the child inherited an ignored SIGINT")

    @staticmethod
    def _reap(child):
        child.kill()
        child.wait()
