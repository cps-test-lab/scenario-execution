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

"""What the nav2 actions share."""


def set_goal_poses(goal_msg, poses):
    """Put the poses in the goal, in the shape the installed nav2_msgs has.

    navigation2 1.5 made the ``poses`` field a ``nav_msgs/Goals`` message -- a header and an
    array -- where it was the array itself before. This is the one place that knows both.
    """
    if hasattr(goal_msg.poses, 'goals'):
        goal_msg.poses.goals = poses
    else:
        goal_msg.poses = poses
