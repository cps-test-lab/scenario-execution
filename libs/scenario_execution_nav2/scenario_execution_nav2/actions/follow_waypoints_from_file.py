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

import json

from .follow_waypoints import FollowWaypoints


class FollowWaypointsFromFile(FollowWaypoints):
    """`follow_waypoints`, with the goal poses read from a JSON file at execute time instead of an
    OSC-declared list.

    A trial driving a waypoint sequence an offline planner precomputed -- tens to hundreds of poses,
    one sequence per (condition, repetition) -- cannot write that sequence into the `.osc` or a
    `.vast` without either file becoming the data store for someone else's planner output. This reads
    it from disk instead, where it already lives as campaign data.

    The file is shaped ``{"repetitions": [{"waypoints": [[...], ...]}, ...]}`` -- one entry of
    ``repetitions`` per stochastic draw of an offline construction step, each holding an ordered list
    of fixed-width rows. `x_index`/`y_index`/`theta_index` say where within each row the pose lives,
    so this stays usable for a caller's own column layout rather than assuming one. `rep` selects
    which repetition (wrapped by ``len(repetitions)``), so a file with only one entry -- a
    deterministic planner's single recorded run -- serves every `rep` value the same way, and a file
    with several serves a different draw per repetition without the caller needing to know which.
    """

    def execute(self, associated_actor, poses_file: str, rep: int = 0,  # pylint: disable=arguments-differ,arguments-renamed
                x_index: int = 2, y_index: int = 3, theta_index: int = 4, loop_count: int = 1) -> None:
        with open(poses_file, encoding="utf-8") as f:
            doc = json.load(f)
        repetitions = doc.get("repetitions")
        if not repetitions:
            raise ValueError(f"{poses_file}: no 'repetitions' to read waypoints from")
        rows = repetitions[rep % len(repetitions)]["waypoints"]
        goal_poses = [
            {
                "position": {"x": float(row[x_index]), "y": float(row[y_index]), "z": 0.0},
                "orientation": {"roll": 0.0, "pitch": 0.0, "yaw": float(row[theta_index])},
            }
            for row in rows
        ]
        super().execute(associated_actor, goal_poses, loop_count)
