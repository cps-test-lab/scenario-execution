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

"""Asking for an adjusted QoS preset must not adjust the preset.

`QoSPresetProfiles.SYSTEM_DEFAULT.value` hands back the enum's own object rather than a copy, so a
profile adjusted in place is the preset itself from then on. One topic asking for a latched
subscription then changes the QoS of every other topic the scenario reads, and those stop matching
publishers that offer exactly what they used to ask for -- as an "incompatible QoS, no messages
will be received" warning on a topic nobody touched.
"""

import unittest

from rclpy.qos import DurabilityPolicy, QoSPresetProfiles, ReliabilityPolicy

from scenario_execution_ros.actions.conversions import get_qos_preset_profile


class TestQosPresetProfiles(unittest.TestCase):

    def test_transient_local_does_not_change_the_shared_preset(self):
        before = QoSPresetProfiles.SYSTEM_DEFAULT.value.durability
        get_qos_preset_profile(('system_default_transient_local',))
        self.assertEqual(QoSPresetProfiles.SYSTEM_DEFAULT.value.durability, before)

    def test_reliable_does_not_change_the_shared_preset(self):
        before = QoSPresetProfiles.SYSTEM_DEFAULT.value.reliability
        get_qos_preset_profile(('system_default_reliable',))
        self.assertEqual(QoSPresetProfiles.SYSTEM_DEFAULT.value.reliability, before)

    def test_a_later_system_default_is_unaffected(self):
        """The failure as a scenario meets it: one topic wants a latched subscription, and the
        next topic asking for the plain default quietly gets the latched one."""
        before = get_qos_preset_profile(('system_default',)).durability
        get_qos_preset_profile(('system_default_transient_local',))
        self.assertEqual(get_qos_preset_profile(('system_default',)).durability, before)

    def test_the_adjusted_profile_is_still_adjusted(self):
        """Copying must not cost the caller what it asked for."""
        self.assertEqual(
            get_qos_preset_profile(('system_default_transient_local',)).durability,
            DurabilityPolicy.TRANSIENT_LOCAL)
        self.assertEqual(
            get_qos_preset_profile(('system_default_reliable',)).reliability,
            ReliabilityPolicy.RELIABLE)

    def test_two_callers_get_profiles_of_their_own(self):
        latched = get_qos_preset_profile(('system_default_transient_local',))
        reliable = get_qos_preset_profile(('system_default_reliable',))
        self.assertIsNot(latched, reliable)
        self.assertEqual(latched.durability, DurabilityPolicy.TRANSIENT_LOCAL)
