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

"""
Test the standalone timing report (python -m scenario_execution.tick_report)
"""
import json
import os
import tempfile
import unittest

from scenario_execution import tick_report
from scenario_execution.utils import tick_recorder


def write_csv(path, fields, rows):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(",".join(fields) + "\n")
        for row in rows:
            handle.write(",".join(str(value) for value in row) + "\n")


class TestTickReport(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write_ticks(self, rows, driver=tick_recorder.DRIVER_ROS_TIMER):
        write_csv(os.path.join(self.dir, tick_recorder.TICK_FILENAME),
                  tick_recorder.TICK_FIELDS,
                  [(index + 1, 1756450000.0 + index * 0.1, index * 0.1,
                    "" if index == 0 else interval, 0.004, 0.1, driver)
                   for index, interval in enumerate(rows)])

    def write_actions(self, rows):
        write_csv(os.path.join(self.dir, tick_recorder.ACTION_FILENAME),
                  tick_recorder.ACTION_FIELDS, rows)

    def test_nothing_recorded_reports_nothing(self):
        """No files at all is 'not measured', and must not be dressed up as a result."""
        self.assertEqual(tick_report.summarize(self.dir), [])

    def test_recorded_but_never_ticked_still_reports(self):
        """Measured and empty is a different statement from not measured."""
        self.write_ticks([])
        lines = tick_report.summarize(self.dir)
        self.assertEqual(len(lines), 1)
        self.assertIn("0 ticks", lines[0])

    def test_late_ticks_are_counted(self):
        self.write_ticks([0.1] * 8 + [0.5, 0.6])
        line = tick_report.summarize(self.dir)[0]
        self.assertIn("2/9 late", line)
        self.assertIn("6.00x", line, "the worst interval against the configured period")

    def test_percentile_withheld_below_the_sample_floor(self):
        """A p95 over a handful of points is not a percentile, so it is not offered."""
        self.write_ticks([0.1] * 5)
        self.assertNotIn("p95", tick_report.summarize(self.dir)[0])
        self.write_ticks([0.1] * 40)
        self.assertIn("p95", tick_report.summarize(self.dir)[0])

    def test_unpaced_driver_reports_no_ratio(self):
        """There is no rate to hold, so a ratio would invite a meaningless comparison."""
        self.write_ticks([0.002] * 40, driver=tick_recorder.DRIVER_SIM_STEP)
        line = tick_report.summarize(self.dir)[0]
        self.assertIn("unpaced", line)
        self.assertNotIn("late", line)

    def test_slowest_actions_are_ranked_by_total_time(self):
        self.write_ticks([0.1] * 3)
        self.write_actions([
            (1, 1756450000.0, 0.0, "id-a", "quick", "pkg.Quick", "update", 0.001, "RUNNING"),
            (2, 1756450000.1, 0.1, "id-a", "quick", "pkg.Quick", "update", 0.001, "RUNNING"),
            (2, 1756450000.1, 0.1, "id-b", "slow", "pkg.Slow", "update", 0.400, "RUNNING"),
        ])
        lines = tick_report.summarize(self.dir)
        self.assertTrue(any("slow" in line for line in lines))
        ranked = [line for line in lines if line.startswith("  ")]
        self.assertIn("slow", ranked[0], "the biggest total comes first")
        self.assertIn("0.400s over 1 call(s)", ranked[0])

    def test_phases_are_ranked_separately(self):
        """A one-shot cost must never be read as a per-tick one."""
        self.write_ticks([0.1] * 2)
        self.write_actions([
            (1, 1756450000.0, 0.0, "id-a", "spawn", "pkg.Spawn", "execute", 0.300, "INVALID"),
            (1, 1756450000.0, 0.0, "id-a", "spawn", "pkg.Spawn", "update", 0.002, "RUNNING"),
        ])
        ranked = [line for line in tick_report.summarize(self.dir) if line.startswith("  ")]
        self.assertEqual(len(ranked), 2)
        self.assertIn("execute", ranked[0])
        self.assertIn("update", ranked[1])

    def test_source_location_used_when_the_behaviour_log_is_there(self):
        """An addition when the other feature was on, never a prerequisite."""
        self.write_ticks([0.1] * 2)
        self.write_actions([
            (1, 1756450000.0, 0.0, "id-a", "spawn", "pkg.Spawn", "update", 0.300, "RUNNING"),
        ])
        without = [line for line in tick_report.summarize(self.dir) if line.startswith("  ")]
        self.assertNotIn("[", without[0])

        with open(os.path.join(self.dir, "behaviors.jsonl"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"format": "behavior_tree_log"}) + "\n")
            handle.write(json.dumps({"behavior_id": "id-a", "osc_file": "/tmp/demo.osc",
                                     "osc_line": 42}) + "\n")
        with_source = [line for line in tick_report.summarize(self.dir) if line.startswith("  ")]
        self.assertIn("[demo.osc:42]", with_source[0])


if __name__ == '__main__':
    unittest.main()
