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

"""The lexer must stay free of semantic predicates, and leading whitespace is ignored.

A `{...}?` predicate reachable from a lexer mode's start closure makes ANTLR set
`suppressEdge` in `LexerATNSimulator.matchATN`, so `dfa.s0` is never assigned and every
single token re-runs full ATN start-state simulation rather than reusing the DFA. The
NEWLINE rule used to carry such a predicate (a start-of-input guard lifted from the Python
grammar) and it cost ~1.2 s to parse a scenario with its imports, against ~0.15 s now.

Nothing about a normal test run reveals a regression here -- everything still passes, just
several times slower -- so these tests assert the mechanism directly.
"""

import unittest

from antlr4 import InputStream, CommonTokenStream
from antlr4.atn.LexerATNSimulator import LexerATNSimulator
from antlr4.error.ErrorListener import ErrorListener

from scenario_execution.osc2_parsing.OpenSCENARIO2Lexer import OpenSCENARIO2Lexer
from scenario_execution.osc2_parsing.OpenSCENARIO2Parser import OpenSCENARIO2Parser

SCENARIO = """import osc.helpers

scenario test_dfa:
    do serial:
        log("x")
"""


def lex_all(text):
    stream = CommonTokenStream(OpenSCENARIO2Lexer(InputStream(text)))
    stream.fill()
    return stream.tokens


class TestLexerHasNoPredicates(unittest.TestCase):

    def test_the_generated_lexer_declares_no_semantic_predicates(self):
        # ANTLR only emits sempred() into the generated class when the grammar has a
        # predicate, so its absence there is the evidence none was reintroduced. It has to
        # be __dict__ rather than hasattr: Recognizer defines an inherited sempred().
        self.assertNotIn(
            "sempred",
            OpenSCENARIO2Lexer.__dict__,
            "the lexer grammar gained a semantic predicate; see this module's docstring "
            "for what that costs",
        )

    def test_the_dfa_start_state_is_memoized_after_lexing(self):
        lex_all(SCENARIO)
        self.assertIsNotNone(
            OpenSCENARIO2Lexer.decisionsToDFA[0].s0,
            "dfa.s0 was not memoized, so every token pays full ATN start-state simulation",
        )

    def test_the_atn_start_state_is_computed_once_not_once_per_token(self):
        original = LexerATNSimulator.matchATN
        calls = []

        def counting_match_atn(simulator, input_stream):
            calls.append(1)
            return original(simulator, input_stream)

        LexerATNSimulator.matchATN = counting_match_atn
        try:
            tokens = lex_all(SCENARIO)
        finally:
            LexerATNSimulator.matchATN = original

        # At most one per lexer mode, and only until the DFA start state is warm -- versus
        # one per token, which is what the predicate used to force.
        self.assertLess(len(calls), len(tokens))


class TestLeadingWhitespace(unittest.TestCase):

    def test_an_indented_first_line_is_accepted(self):
        # Dropping the start-of-input predicate widened the accepted language slightly:
        # leading whitespace on the first line is now skipped by SKIP_ rather than turned
        # into an INDENT that no rule could consume. Pinned here because it is a language
        # change, not an implementation detail.
        errors = []

        class Collect(ErrorListener):
            def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # pylint: disable=invalid-name
                errors.append(f"line {line}:{column} {msg}")

        parser = OpenSCENARIO2Parser(CommonTokenStream(OpenSCENARIO2Lexer(InputStream("    " + SCENARIO))))
        parser.removeErrorListeners()
        parser.addErrorListener(Collect())
        parser.osc_file()
        self.assertEqual(errors, [])

    def test_leading_whitespace_does_not_change_the_token_stream(self):
        plain = [(t.type, t.text) for t in lex_all(SCENARIO)]
        indented = [(t.type, t.text) for t in lex_all("    " + SCENARIO)]
        self.assertEqual(plain, indented)
