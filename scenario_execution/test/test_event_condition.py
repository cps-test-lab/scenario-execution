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

"""The event conditions wait, until and ``@event if`` take: any boolean expression, rise() and fall().

The tree is ticked by hand and the variables are set between ticks, so each test states exactly on
which tick a condition is met.
"""

import unittest

import py_trees
from antlr4.InputStream import InputStream
from py_trees.common import Status

from scenario_execution.model.model_blackboard import create_py_tree_blackboard
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.utils.logging import Logger

HEADER = """
struct robot_state:
    var docked: bool = false

scenario test:
    robot: robot_state
    event ev
    var tripped: bool = false
    var docked: bool = true
    var clearance: float = 1.0
    var count: int = 0
    flag: bool = true
    do serial:
"""


class TestEventCondition(unittest.TestCase):
    # pylint: disable=missing-function-docstring, too-many-public-methods

    def setUp(self) -> None:
        py_trees.blackboard.Blackboard.clear()
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.tree = None

    def build(self, body):
        tree = py_trees.composites.Sequence(name="", memory=True)
        parsed_tree = self.parser.parse_input_stream(InputStream(HEADER + body))
        model = self.parser.create_internal_model(parsed_tree, tree, "test.osc", False)
        create_py_tree_blackboard(model, tree, self.parser.logger, False)
        self.tree = py_trees.trees.BehaviourTree(create_py_tree(model, tree, self.parser.logger, False))
        return self.tree

    def tick(self):
        self.tree.tick()
        return self.tree.root.status

    @staticmethod
    def set(name, value):
        py_trees.blackboard.Blackboard.set(f'/test/{name}', value)

    def assert_ends_when(self, body, name, value):
        """The scenario runs until *name* is set to *value*, and ends on the next tick."""
        self.build(body)
        self.assertEqual(Status.RUNNING, self.tick())
        self.assertEqual(Status.RUNNING, self.tick())
        self.set(name, value)
        self.assertEqual(Status.SUCCESS, self.tick())

    #########
    # a boolean expression
    #########

    def test_bare_bool_variable(self):
        self.assert_ends_when("        wait tripped\n", 'tripped', True)

    def test_bare_bool_variable_already_true(self):
        self.build("        wait docked\n")
        self.assertEqual(Status.SUCCESS, self.tick())

    def test_member_access(self):
        self.assert_ends_when("        wait robot.docked\n", 'robot/docked', True)

    def test_not(self):
        self.assert_ends_when("        wait not docked\n", 'docked', False)

    def test_parenthesised(self):
        self.assert_ends_when("        wait (tripped and not robot.docked)\n", 'tripped', True)

    def test_bool_parameter(self):
        self.build("        wait flag\n")
        self.assertEqual(Status.SUCCESS, self.tick())

    def test_comparison_still_works(self):
        self.assert_ends_when("        wait clearance < 0.3\n", 'clearance', 0.2)

    def test_non_bool_variable_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.build("        wait count\n")
        self.assertIn("count", str(caught.exception))
        self.assertIn("int", str(caught.exception))

    def test_non_bool_operand_of_not_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            self.build("        wait not clearance\n")
        self.assertIn("float", str(caught.exception))

    def test_non_bool_value_at_runtime_fails_naming_the_condition(self):
        self.build("        wait tripped\n")
        self.assertEqual(Status.RUNNING, self.tick())
        self.set('tripped', 1)
        # Truthiness would have read 1 as met; a condition that is not a bool is a scenario error.
        self.assertEqual(Status.FAILURE, self.tick())
        condition = self.tree.root.children[0].children[0]
        self.assertIn("tripped", condition.feedback_message)
        self.assertIn("int", condition.feedback_message)

    #########
    # rise() and fall()
    #########

    def test_rise(self):
        self.assert_ends_when("        wait rise(tripped)\n", 'tripped', True)

    def test_rise_of_a_comparison(self):
        self.assert_ends_when("        wait rise(clearance < 0.3)\n", 'clearance', 0.2)

    def test_rise_needs_a_transition_when_already_true(self):
        self.build("        wait rise(docked)\n")
        self.assertEqual(Status.RUNNING, self.tick())
        self.assertEqual(Status.RUNNING, self.tick())
        self.set('docked', False)
        self.assertEqual(Status.RUNNING, self.tick())
        self.set('docked', True)
        self.assertEqual(Status.SUCCESS, self.tick())

    def test_fall(self):
        self.assert_ends_when("        wait fall(docked)\n", 'docked', False)

    def test_fall_needs_a_transition_when_already_false(self):
        self.build("        wait fall(tripped)\n")
        self.assertEqual(Status.RUNNING, self.tick())
        self.set('tripped', True)
        self.assertEqual(Status.RUNNING, self.tick())
        self.set('tripped', False)
        self.assertEqual(Status.SUCCESS, self.tick())

    def test_rise_takes_its_reference_when_the_wait_starts(self):
        # The second wait starts after the variable is already true: that is its reference, not a rise.
        self.build("        wait tripped\n        wait rise(tripped)\n")
        self.assertEqual(Status.RUNNING, self.tick())
        self.set('tripped', True)
        self.assertEqual(Status.RUNNING, self.tick())
        self.assertEqual(Status.RUNNING, self.tick())

    def test_rise_of_a_non_bool_is_refused(self):
        self.assertRaises(ValueError, self.build, "        wait rise(count)\n")

    def test_every_is_refused_naming_it(self):
        with self.assertRaises(ValueError) as caught:
            self.build("        wait every(1s)\n")
        self.assertIn("every()", str(caught.exception))

    #########
    # @event if <condition>
    #########

    def test_event_guarded_by_bool_variable(self):
        self.build("        wait @ev if tripped\n")
        self.set('ev', True)
        self.assertEqual(Status.RUNNING, self.tick())
        self.set('tripped', True)
        self.assertEqual(Status.SUCCESS, self.tick())

    #########
    # until
    #########

    def until(self, condition):
        return f"""        serial:
            wait false
        with:
            until {condition}
"""

    def test_until_bare_bool(self):
        self.assert_ends_when(self.until("tripped"), 'tripped', True)

    def test_until_member_access(self):
        self.assert_ends_when(self.until("robot.docked"), 'robot/docked', True)

    def test_until_not(self):
        self.assert_ends_when(self.until("not docked"), 'docked', False)

    def test_until_rise(self):
        self.assert_ends_when(self.until("rise(clearance < 0.3)"), 'clearance', 0.2)

    def test_until_fall(self):
        self.assert_ends_when(self.until("fall(docked)"), 'docked', False)

    def test_until_event_guarded_by_bool(self):
        self.build(self.until("@ev if not docked"))
        self.set('ev', True)
        self.assertEqual(Status.RUNNING, self.tick())
        self.set('docked', False)
        self.assertEqual(Status.SUCCESS, self.tick())


if __name__ == '__main__':
    unittest.main()
