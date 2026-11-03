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
"""A trial's time budget can be a parameter, and has to be a duration.

ASAM OpenSCENARIO DSL: ``elapsed-expression: 'elapsed' '(' duration-expression ')'`` with
``duration-expression: expression``. The form is unconstrained -- a literal, a parameter, an
expression -- and what it must resolve to is a *duration*.
"""

import unittest

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.osc2_parser import OpenScenario2Parser

from .common import DebugLogger


class TestElapsedParameter(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        self.logger = DebugLogger("")
        self.parser = OpenScenario2Parser(self.logger)
        self.tree = py_trees.composites.Sequence(name="", memory=True)

    def _build(self, content: str):
        parsed = self.parser.parse_input_stream(InputStream(content))
        model = self.parser.create_internal_model(parsed, self.tree, "test.osc", False)
        return create_py_tree(model, self.tree, self.parser.logger, False)

    def _waits(self, built) -> list:
        return [b.name for b in built.iterate() if "wait" in getattr(b, "name", "")]

    def test_a_literal_duration_still_works(self):
        built = self._build(
            "import osc.helpers\n"
            "\n"
            "scenario t:\n"
            "    do serial:\n"
            "        wait elapsed(3s)\n")
        self.assertIn("wait 3.0s", self._waits(built))

    def test_a_parameter_holding_a_duration_is_accepted(self):
        """The reported case. The grammar always allowed it (`durationExpression : expression`);
        only the visitor refused, so a scenario could not take its own budget as a parameter and
        a campaign had no way to sweep one."""
        built = self._build(
            "import osc.helpers\n"
            "\n"
            "scenario t:\n"
            "    budget: time = 7s\n"
            "    do serial:\n"
            "        wait elapsed(budget)\n")
        # Not merely that it parsed: the parameter's VALUE has to reach the timer.
        self.assertIn("wait 7.0s", self._waits(built))

    def _refusal(self, declaration: str, argument: str) -> str:
        with self.assertRaises(ValueError) as caught:
            self._build(
                "import osc.helpers\n"
                "\n"
                "scenario t:\n"
                f"    {declaration}\n"
                "    do serial:\n"
                f"        wait elapsed({argument})\n")
        return str(caught.exception)

    def test_a_parameter_that_is_not_a_duration_is_refused(self):
        """A quantity that is not a time is not a duration, however plausible the number.

        `d: length = 7m` used here would have waited seven seconds -- the unit is dropped and the
        magnitude taken as seconds, which is a wrong trial rather than a failed one.
        """
        message = self._refusal("d: length = 7m", "d")
        self.assertIn("needs a duration", message)
        self.assertIn("length", message)

    def test_a_unitless_parameter_is_refused(self):
        """An int carries no unit, so nothing says it means seconds."""
        self.assertIn("is int", self._refusal("n: int = 7", "n"))

    def test_a_literal_of_the_wrong_quantity_is_refused_too(self):
        """The same rule for a literal, which is where it was already being broken.

        `elapsed(7m)` was accepted and waited 7 s. Checked here rather than only for parameters,
        because a rule that holds for one form and not the other is the gap this whole entry is
        about.
        """
        with self.assertRaises(ValueError) as caught:
            self._build(
                "import osc.helpers\n"
                "\n"
                "scenario t:\n"
                "    do serial:\n"
                "        wait elapsed(7m)\n")
        self.assertIn("needs a duration", str(caught.exception))
