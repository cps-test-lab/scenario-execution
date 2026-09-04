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

"""The keyword table in docs/openscenarioDSL.rst is a conformance claim, so it is checked.

A mark that has drifted is not a cosmetic problem: a stale cross sends a reader building a
workaround for something that works, and a stale tick sends them writing a scenario that fails at
tree build. Every row gets a scenario here, and the mark is asserted against what building it does.
"""

import os
import re
import unittest

import py_trees
from antlr4.InputStream import InputStream

from scenario_execution.model.model_blackboard import create_py_tree_blackboard
from scenario_execution.model.model_to_py_tree import create_py_tree
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.utils.logging import Logger

DOC = os.path.join(os.path.dirname(__file__), '..', '..', 'docs', 'openscenarioDSL.rst')
ROW = re.compile(r'^``(\w+)``\s+:raw-html:`&#(\d+);`')
TICK = '9989'

# Every probe below is a scenario, so these three cannot be probed separately -- a regression in any
# of them fails all 48 other cases at once.
EXERCISED_EVERYWHERE = {'import', 'scenario', 'do'}

_H = "import osc.helpers\n\n"
_EXT = "scenario_execution.external_methods.common.get_output_directory()"
_DEF = f"    def outdir() -> string is external {_EXT}\n"

PROBES = {
    'action': _H + "action my_action:\n    p: string\n\nscenario t:\n    do serial:\n        log('a')\n",
    'actor': _H + "actor my_actor:\n    p: string = 'x'\n\nscenario t:\n    do serial:\n        log('a')\n",
    'as': _H + "scenario t:\n    event ev\n    var x: int = 0\n    do serial:\n        wait @ev as e if x == 1\n",
    'bool': _H + "scenario t:\n    var b: bool = true\n    do serial:\n        wait b == true\n",
    'call': _H + "scenario t:\n    do serial:\n        call log(true)\n",
    'cover': _H + "scenario t:\n    cover()\n    do serial:\n        log('a')\n",
    'def': _H + "scenario t:\n" + _DEF + "    do serial:\n        log(outdir())\n",
    'default': _H + "scenario t:\n    do serial:\n        log('a') with:\n            keep(default it.msg == 'a')\n",
    'elapsed': _H + "scenario t:\n    do serial:\n        wait elapsed(0.1s)\n",
    'emit': _H + "scenario t:\n    do serial:\n        emit end\n",
    'enum': _H + "enum color: [red, green]\n\nscenario t:\n    do serial:\n        log('a')\n",
    'event': _H + "scenario t:\n    event ev\n    do serial:\n        emit ev\n",
    'every': _H + "scenario t:\n    do serial:\n        wait every(1s)\n",
    'expression': _H + "scenario t:\n    def two() -> int is expression 1 + 1\n    do serial:\n        log('a')\n",
    'extend': _H + "struct my_struct:\n    a: int\n\nextend my_struct:\n    b: int\n\nscenario t:\n    do serial:\n        log('a')\n",
    'external': _H + "scenario t:\n" + _DEF + "    do serial:\n        log(outdir())\n",
    'fall': _H + "scenario t:\n    var b: bool = true\n    do serial:\n        wait fall(b)\n",
    'float': _H + "scenario t:\n    var f: float = 1.5\n    do serial:\n        wait f == 1.5\n",
    'global': _H + "global g: int = 1\n\nscenario t:\n    do serial:\n        log('a')\n",
    'hard': _H + "scenario t:\n    do serial:\n        log('a') with:\n            keep(hard it.msg == 'a')\n",
    'if': _H + "scenario t:\n    event ev\n    var x: int = 0\n    do serial:\n        wait @ev if x == 1\n",
    'inherits': _H + "struct a:\n    x: int\n\nstruct b inherits a:\n    y: int\n\nscenario t:\n    do serial:\n        log('a')\n",
    'int': _H + "scenario t:\n    var i: int = 1\n    do serial:\n        wait i == 1\n",
    'is': _H + "scenario t:\n" + _DEF + "    do serial:\n        log(outdir())\n",
    'it': _H + "scenario t:\n    do serial:\n        log('a') with:\n            keep(it.msg == 'a')\n",
    'keep': _H + "scenario t:\n    do serial:\n        log('a') with:\n            keep(it.msg == 'a')\n",
    'list': _H + "scenario t:\n    var l: list of int = [1, 2]\n    do serial:\n        log('a')\n",
    'of': _H + "scenario t:\n    var l: list of int = [1, 2]\n    do serial:\n        log('a')\n",
    'on': _H + "scenario t:\n    event ev\n    on @ev:\n        emit end\n    do serial:\n        emit end\n",
    'one_of': _H + "scenario t:\n    do serial:\n        one_of:\n            log('a')\n            log('b')\n",
    'only': _H + f"scenario t:\n    def outdir() -> string is only external {_EXT}\n    do serial:\n        log(outdir())\n",
    'parallel': _H + "scenario t:\n    do parallel:\n        log('a')\n        log('b')\n",
    'range': _H + "scenario t:\n    do serial:\n        log('a') with:\n            keep(it.msg in ['a'..'b'])\n",
    'record': _H + "scenario t:\n    record()\n    do serial:\n        log('a')\n",
    'remove_default': _H + "struct base:\n    p: string = 'base'\n\nstruct derived inherits base:\n    remove_default(p)\n\nscenario t:\n    do serial:\n        log('a')\n",
    'rise': _H + "scenario t:\n    var b: bool = false\n    do serial:\n        wait rise(b)\n",
    'serial': _H + "scenario t:\n    do serial:\n        log('a')\n",
    'SI': _H + "type len2 is SI(m: 1)\n\nscenario t:\n    do serial:\n        log('a')\n",
    'string': _H + "scenario t:\n    var text: string = 'x'\n    do serial:\n        log(text)\n",
    'struct': _H + "struct my_struct:\n    a: int\n\nscenario t:\n    do serial:\n        log('a')\n",
    'type': _H + "type len2 is SI(m: 1)\n\nscenario t:\n    do serial:\n        log('a')\n",
    'uint': _H + "scenario t:\n    var u: uint = 1\n    do serial:\n        wait u == 1\n",
    'undefined': _H + "scenario t:\n    def two() -> int is undefined\n    do serial:\n        log('a')\n",
    'unit': _H + "type len2 is SI(m: 1)\nunit metre of len2 is SI(m: 1, factor: 1)\n\nscenario t:\n    do serial:\n        log('a')\n",
    'until': _H + "scenario t:\n    event ev\n    do serial:\n        log('a') with:\n            until @ev\n",
    'var': _H + "scenario t:\n    var i: int = 1\n    do serial:\n        wait i == 1\n",
    'wait': _H + "scenario t:\n    do serial:\n        wait elapsed(0.1s)\n",
    'with': _H + "scenario t:\n    do serial:\n        log('a') with:\n            failure_is_success()\n",
}


class TestKeywordSupportTable(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    @staticmethod
    def documented_marks():
        marks = {}
        with open(DOC, encoding='utf-8') as handle:
            for line in handle:
                match = ROW.match(line.strip())
                if match:
                    marks[match.group(1)] = match.group(2) == TICK
        return marks

    @staticmethod
    def parse(scenario_content):
        parser = OpenScenario2Parser(Logger('test', False))
        return parser, parser.parse_input_stream(InputStream(scenario_content))

    @staticmethod
    def build(parser, parsed_tree):
        tree = py_trees.composites.Sequence(name="", memory=True)
        model = parser.create_internal_model(parsed_tree, tree, "test.osc", False)
        create_py_tree_blackboard(model, tree, parser.logger, False)
        create_py_tree(model, tree, parser.logger, False)

    def test_the_table_is_readable(self):
        self.assertTrue(os.path.exists(DOC), f"keyword table not found at {os.path.abspath(DOC)}")
        self.assertTrue(self.documented_marks(), "no keyword rows parsed out of the table")

    def test_every_row_is_covered(self):
        # A keyword added to the table without a probe would become the next stale mark unnoticed.
        documented = set(self.documented_marks())
        self.assertEqual(set(), documented - set(PROBES) - EXERCISED_EVERYWHERE,
                         "keyword documented but not probed")
        self.assertEqual(set(), set(PROBES) - documented, "keyword probed but not documented")

    def test_marks_match_what_the_code_does(self):
        for keyword, supported in self.documented_marks().items():
            if keyword in EXERCISED_EVERYWHERE:
                continue
            with self.subTest(keyword=keyword):
                parser, parsed_tree = self.parse(PROBES[keyword])
                if supported:
                    self.build(parser, parsed_tree)
                else:
                    # The probe has to parse: a refusal that is really a typo in the scenario would
                    # let a wrong mark pass unnoticed.
                    self.assertRaises(ValueError, self.build, parser, parsed_tree)
