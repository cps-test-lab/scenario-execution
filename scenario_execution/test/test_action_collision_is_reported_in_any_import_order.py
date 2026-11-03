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

"""Two imported libraries declaring one action name is reported the same way in either order.

Name resolution takes the first declaration it walks past, and the arguments of the call are then
checked against that one. So the import order decided what the author was told: put the other
library first and the very same scenario is refused for an argument name that is perfectly good
in the library it meant -- a message that names neither the collision nor the library it came
from, and sends the reader to fix a call that is not wrong.
"""

import os
import tempfile
import unittest

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution.model.error import OSC2ParsingError
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.utils.logging import Logger

# Two libraries, each declaring `place_it` with parameters of its own. The names differ so that
# a call written for one is refused by the other -- which is what made the order visible.
LIB_A = """
action place_it:
    entity: string
"""

LIB_B = """
action place_it:
    entity_name: string
"""

SCENARIO = """
import "{first}"
import "{second}"

scenario test:
    do serial:
        place_it(entity: 'robot')
"""


class TestActionCollisionIsReportedInAnyImportOrder(unittest.TestCase):

    def setUp(self):
        self.parser = OpenScenario2Parser(Logger('test', False))
        self.tree = py_trees.composites.Sequence(name="", memory=True)
        self._dir = tempfile.TemporaryDirectory()
        self.a = os.path.join(self._dir.name, "lib_a.osc")
        self.b = os.path.join(self._dir.name, "lib_b.osc")
        with open(self.a, "w", encoding="utf-8") as handle:
            handle.write(LIB_A)
        with open(self.b, "w", encoding="utf-8") as handle:
            handle.write(LIB_B)

    def tearDown(self):
        self._dir.cleanup()

    def _parse(self, first, second):
        content = SCENARIO.format(first=first, second=second)
        parsed = self.parser.parse_input_stream(InputStream(content))
        return self.parser.create_internal_model(parsed, self.tree, "test.osc", False)

    def _refusal(self, first, second) -> str:
        with self.assertRaises((OSC2ParsingError, ValueError)) as caught:
            self._parse(first, second)
        exc = caught.exception
        return getattr(exc, "msg", None) or str(exc)

    def test_the_library_whose_signature_matches_first(self):
        """`lib_a` declares the parameter this call uses, so nothing about the CALL is wrong."""
        message = self._refusal(self.a, self.b)
        self.assertIn('declared by more than one imported library', message)
        self.assertIn('lib_a.osc', message)
        self.assertIn('lib_b.osc', message)

    def test_the_other_library_first(self):
        """The order that used to report `Named argument entity unknown` instead."""
        message = self._refusal(self.b, self.a)
        self.assertIn('declared by more than one imported library', message)
        self.assertNotIn('Named argument', message)
        self.assertIn('lib_a.osc', message)
        self.assertIn('lib_b.osc', message)

    def test_a_declaration_beside_its_use_is_not_a_library_collision(self):
        """Only two IMPORTED libraries are ambiguous.

        A declaration in the file the call is written in is the author's own. Which of the two
        name resolution then picks is unchanged by this check -- reporting that case would refuse
        scenarios that already run.
        """
        content = """
import "%s"

action place_it:
    entity: string

scenario test:
    do serial:
        place_it(entity: 'robot')
""" % self.a
        parsed = self.parser.parse_input_stream(InputStream(content))
        self.assertIsNotNone(
            self.parser.create_internal_model(parsed, self.tree, "test.osc", False))

    def test_one_library_alone_still_parses(self):
        """The check must fire on the collision, not on the name."""
        content = """
import "%s"

scenario test:
    do serial:
        place_it(entity: 'robot')
""" % self.a
        parsed = self.parser.parse_input_stream(InputStream(content))
        self.assertIsNotNone(self.parser.create_internal_model(parsed, self.tree, "test.osc", False))


if __name__ == '__main__':
    unittest.main()
