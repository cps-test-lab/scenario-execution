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
"""A parameter that is its own value is refused, not recursed into."""

import unittest

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution.model.error import OSC2ParsingError
from scenario_execution.model.osc2_parser import OpenScenario2Parser

from .common import DebugLogger


class TestSelfReferentialParameter(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        self.logger = DebugLogger("")
        self.parser = OpenScenario2Parser(self.logger)
        self.tree = py_trees.composites.Sequence(name="", memory=True)

    def _model(self, content: str):
        parsed = self.parser.parse_input_stream(InputStream(content))
        return self.parser.create_internal_model(parsed, self.tree, "test.osc", False)

    def test_an_argument_repeating_a_field_name_is_refused_with_a_place(self):
        """The reported case. `spot(x: x)` binds the argument's value to the struct's own field
        `x` rather than to the scenario's `x`, so the field becomes its own default. It used to
        recurse until Python gave out -- and a RecursionError names no parameter, no file and no
        line, which made this the one construct that produced a traceback instead of a diagnostic.
        """
        # OSC2ParsingError, not a wrapped ValueError: the cycle is met while the scenario's
        # own parameters are being resolved, which is outside resolve_internal_model's wrapper.
        with self.assertRaises(OSC2ParsingError) as caught:
            self._model(
                "import osc.helpers\n"
                "\n"
                "struct spot:\n"
                "    x: length = 1.0m\n"
                "\n"
                "scenario t:\n"
                "    x: length = 2.0m\n"
                "    p: spot = spot(x: x)\n"
                "    do serial:\n"
                "        wait elapsed(1s)\n")
        message = str(caught.exception)
        self.assertIn('"x" is its own value', message)
        self.assertIn("line: 8", message)   # where it is written, not a recursion depth

    def test_a_differently_named_argument_still_resolves(self):
        """The guard must not refuse the ordinary case it sits next to: the same struct filled
        from a parameter whose name does not collide."""
        model = self._model(
            "import osc.helpers\n"
            "\n"
            "struct spot:\n"
            "    x: length = 1.0m\n"
            "\n"
            "scenario t:\n"
            "    start: length = 2.0m\n"
            "    p: spot = spot(x: start)\n"
            "    do serial:\n"
            "        wait elapsed(1s)\n")
        self.assertIsNotNone(model)

    def test_a_struct_left_at_its_own_default_still_resolves(self):
        """And the case with no argument at all."""
        model = self._model(
            "import osc.helpers\n"
            "\n"
            "struct spot:\n"
            "    x: length = 1.0m\n"
            "\n"
            "scenario t:\n"
            "    p: spot = spot()\n"
            "    do serial:\n"
            "        wait elapsed(1s)\n")
        self.assertIsNotNone(model)
