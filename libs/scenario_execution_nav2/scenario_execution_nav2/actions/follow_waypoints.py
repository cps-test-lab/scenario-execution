# Copyright (C) 2024 Intel Corporation
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

import numbers

from nav2_msgs.action import FollowWaypoints as FollowWaypointsAction

from scenario_execution_ros.actions.common import get_pose_stamped

from .common import set_goal_poses
from scenario_execution_ros.actions.ros_action_call import RosActionCall, ActionCallActionState


def describe_missed_waypoint(missed):
    """One entry of a FollowWaypoints result's ``missed_waypoints``, as text.

    The entry's shape depends on the installed nav2_msgs: a bare index (``int32[]``), a
    ``MissedWaypoint`` (``index``, ``error_code``) or a ``WaypointStatus`` (``waypoint_index``,
    ``error_code``, ``error_msg``). Indices are nav2's, counted from 0.
    """
    if isinstance(missed, numbers.Integral):
        return f"index {missed}"
    index = getattr(missed, "waypoint_index", getattr(missed, "index", None))
    details = []
    error_code = getattr(missed, "error_code", None)
    if error_code:
        details.append(f"error {error_code}")
    error_msg = getattr(missed, "error_msg", "")
    if error_msg:
        details.append(error_msg)
    text = f"index {index}"
    if details:
        text += f" ({': '.join(details)})"
    return text


def describe_missed_waypoints(result):
    """What a FollowWaypoints result says was missed, or None if every waypoint was reached."""
    missed = list(getattr(result, "missed_waypoints", None) or [])
    if not missed:
        return None
    return f"{len(missed)} waypoint(s) missed: " + ", ".join(describe_missed_waypoint(entry) for entry in missed)


class FollowWaypoints(RosActionCall):
    """
    Class to follow waypoints
    """

    def __init__(self, associated_actor, action_topic: str, namespace_override: str, success_on_acceptance: bool,
                 allow_missed_waypoints: bool = False) -> None:
        self.namespace = associated_actor["namespace"]
        if namespace_override:
            self.namespace = namespace_override
        self.goal_poses = None
        self.loop_count = 0
        self.allow_missed_waypoints = allow_missed_waypoints
        #: What the last result said was missed, when missed waypoints are allowed.
        self.missed_waypoints_summary = None
        super().__init__(self.namespace + '/' + action_topic, "nav2_msgs.action.FollowWaypoints", success_on_acceptance=success_on_acceptance)
        self.resolve_variable_reference_arguments_in_execute = True

    def execute(self, associated_actor, goal_poses: list, loop_count: int = 1) -> None:  # pylint: disable=arguments-differ,arguments-renamed
        self.goal_poses = goal_poses
        self.loop_count = loop_count
        self.missed_waypoints_summary = None
        super().execute("")

    def get_goal_msg(self):
        goal_msg = FollowWaypointsAction.Goal()
        now = self.node.get_clock().now().to_msg()
        set_goal_poses(goal_msg, [get_pose_stamped(now, pose) for pose in self.goal_poses])
        if hasattr(goal_msg, "number_of_loops"):
            goal_msg.number_of_loops = max(0, int(self.loop_count))
        return goal_msg

    def check_result(self, result):
        """Fail a goal nav2 succeeded although waypoints were missed.

        With ``stop_on_failure: false`` the waypoint follower moves on past a waypoint it could not
        reach and succeeds the goal at the end of the list; the failures are only in the result's
        ``missed_waypoints``. A stack that reaches none of them still reports success that way.
        """
        summary = describe_missed_waypoints(result)
        if summary is None:
            return None
        error_msg = getattr(result, "error_msg", "")
        if error_msg:
            summary += f" ({error_msg})"
        if self.allow_missed_waypoints:
            self.missed_waypoints_summary = summary
            self.logger.warning(f"Goal succeeded with {summary}, allowed by allow_missed_waypoints.")
            return None
        return f"Goal succeeded, but {summary}"

    def get_feedback_message(self, current_state):
        feedback_message = super().get_feedback_message(current_state)

        if self.current_state == ActionCallActionState.IDLE:
            feedback_message = "Waiting for navigation"
        elif self.current_state == ActionCallActionState.ACTION_CALLED:
            if self.received_feedback:
                current_waypoint = getattr(self.received_feedback, "current_waypoint", None)
                if current_waypoint is not None:
                    feedback_message = f"Heading to waypoint {current_waypoint + 1} of {len(self.goal_poses)}."
                else:
                    feedback_message = f"Executing waypoint following to ({self.goal_poses})."
            else:
                feedback_message = f"Executing waypoint following to ({self.goal_poses})."
        elif current_state == ActionCallActionState.DONE:
            if self.missed_waypoints_summary:
                feedback_message = f"Waypoints followed, {self.missed_waypoints_summary}"
            else:
                feedback_message = "Waypoints reached."
        return feedback_message
