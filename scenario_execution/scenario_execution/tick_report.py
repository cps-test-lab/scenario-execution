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

"""Read the timing records of a run and say whether the tick rate was held.

Standard library only, and usable on its own::

    python -m scenario_execution.tick_report <output-dir>

Answers the two questions in order. Was the rate held -- the achieved interval
against the configured period, and how often a tick was late. If it was not, where
did the time go -- which actions spent it, split by phase so a one-shot cost is
never read as a per-tick one.

This is also what produces the summary logged at the end of a recorded run: the
files are read back after they are closed rather than tracked while ticking, so
there is one implementation of the arithmetic and the tick loop carries no
bookkeeping for it.

If the behaviour-tree log is present it is used to name the ``.osc`` file and line
an action came from. Absent, everything else still works -- the timing records name
the action themselves.
"""

import csv
import json
import os
import sys

from scenario_execution.utils import bt_logger, tick_recorder

#: A tick is "late" beyond this multiple of the configured period. Reporting only:
#: it decides what this summary highlights, never what a scenario's result is.
LATE_FACTOR = 1.5

#: Do not describe a tail from a handful of samples. A p95 over seven points is the
#: maximum wearing a percentile's name, so below this only the plain numbers are
#: reported.
MIN_TICKS_FOR_PERCENTILE = 30

TOP_ACTIONS = 5


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(values, fraction):
    """Nearest-rank percentile of a non-empty, unsorted list."""
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * len(ordered) + 0.5)) - 1))
    return ordered[index]


def read_ticks(output_dir):
    path = os.path.join(output_dir, tick_recorder.TICK_FILENAME)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_actions(output_dir):
    path = os.path.join(output_dir, tick_recorder.ACTION_FILENAME)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_sources(output_dir):
    """``behavior_id`` -> ``file:line``, from the behaviour-tree log if it is there.

    Optional by design: the timing records carry their own identity, so this only
    adds the scenario source location when the other feature was enabled too.
    """
    path = os.path.join(output_dir, bt_logger.DEFAULT_FILENAME)
    sources = {}
    if not os.path.isfile(path):
        return sources
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except ValueError:
                continue
            osc_file = record.get("osc_file")
            behavior_id = record.get("behavior_id")
            if osc_file and behavior_id and behavior_id not in sources:
                sources[behavior_id] = f"{os.path.basename(osc_file)}:{record.get('osc_line')}"
    return sources


def _tick_lines(ticks):
    intervals = [(_float(row["interval_s"]), _float(row["period_s"])) for row in ticks]
    ratios = [interval / period for interval, period in intervals
              if interval is not None and period]
    driver = ticks[-1]["driver"] if ticks else ""
    if driver == tick_recorder.DRIVER_SIM_STEP:
        # Unpaced: there is no rate to hold, so reporting a ratio against the step
        # size would invite a comparison that means nothing.
        return [f"Tick timing: {len(ticks)} ticks, driver '{driver}' (unpaced; no tick rate to hold)"]
    if not ratios:
        return [f"Tick timing: {len(ticks)} ticks, driver '{driver}'"]
    late = sum(1 for ratio in ratios if ratio > LATE_FACTOR)
    summary = (f"Tick timing: {len(ticks)} ticks, driver '{driver}', "
               f"max {max(ratios):.2f}x the configured period, "
               f"{late}/{len(ratios)} late (>{LATE_FACTOR}x)")
    if len(ratios) >= MIN_TICKS_FOR_PERCENTILE:
        summary += f", p95 {_percentile(ratios, 0.95):.2f}x"
    return [summary]


def _action_lines(actions, sources):
    totals = {}
    for row in actions:
        duration = _float(row["duration_s"])
        if duration is None:
            continue
        key = (row["behavior_id"], row["behavior_name"], row["phase"])
        total, worst, calls = totals.get(key, (0.0, 0.0, 0))
        totals[key] = (total + duration, max(worst, duration), calls + 1)
    if not totals:
        return []
    ranked = sorted(totals.items(), key=lambda item: item[1][0], reverse=True)[:TOP_ACTIONS]
    lines = [f"Action timing, slowest by total time (top {len(ranked)}):"]
    for (behavior_id, name, phase), (total, worst, calls) in ranked:
        where = sources.get(behavior_id)
        location = f" [{where}]" if where else ""
        lines.append(f"  {name}{location} {phase}: {total:.3f}s over {calls} call(s), "
                     f"worst {worst:.3f}s")
    return lines


def summarize(output_dir):
    """Human-readable summary lines for the records in *output_dir*.

    Returns an empty list when nothing was recorded. A recorded run that never
    ticked returns the header line with zero ticks -- measured and empty, which is
    a different statement from not measured.
    """
    ticks = read_ticks(output_dir)
    actions = read_actions(output_dir)
    if ticks is None and actions is None:
        return []
    lines = []
    if ticks is not None:
        lines.extend(_tick_lines(ticks))
    if actions:
        lines.extend(_action_lines(actions, read_sources(output_dir)))
    return lines


def main():
    if len(sys.argv) != 2:
        print(f"usage: python -m {__spec__.name if __spec__ else 'scenario_execution.tick_report'} "
              "<output-dir>", file=sys.stderr)
        return 2
    output_dir = sys.argv[1]
    lines = summarize(output_dir)
    if not lines:
        print(f"No timing records in '{output_dir}'. Was the scenario run with --tick-log?",
              file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
