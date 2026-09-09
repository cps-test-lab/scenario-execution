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
"""An .osc file is source text, and source text is UTF-8."""

import os
import tempfile
import unittest

from scenario_execution.model.osc2_parser import OpenScenario2Parser

from .common import DebugLogger

_SCENARIO = """\
import osc.standard.base

scenario test:
    # a comment with an en-dash – and a degree sign 20°C
    do serial:
        wait elapsed(1s)
"""

_LATIN1_SCENARIO = """\
import osc.standard.base

scenario test:
    # a comment at 20°C
    do serial:
        wait elapsed(1s)
"""


class TestParserEncoding(unittest.TestCase):
    # pylint: disable=missing-function-docstring

    def setUp(self) -> None:
        self.parser = OpenScenario2Parser(DebugLogger(""))
        self.dir = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with

    def tearDown(self) -> None:
        self.dir.cleanup()

    def _write(self, text: str, encoding: str = "utf-8") -> str:
        path = os.path.join(self.dir.name, "scenario.osc")
        with open(path, "wb") as handle:
            handle.write(text.encode(encoding))
        return path

    def test_a_non_ascii_character_in_a_comment_parses(self):
        """The reported case. One en-dash used to abort the parse before any token was read,
        so a whole campaign failed at generation on a character every editor writes."""
        model = self.parser.parse_file(self._write(_SCENARIO), False)
        self.assertIsNotNone(model)

    def test_a_file_that_is_not_utf8_is_refused_with_a_line_and_column(self):
        """A genuinely mis-encoded file still fails -- but as a place to go and edit.

        A byte offset is neither a line nor a column, and the file cannot be decoded, so
        nothing downstream can convert one. The message therefore has to carry it.
        """
        # A degree sign, which latin-1 writes as the single byte 0xB0 -- valid there and
        # invalid as UTF-8, which is what a genuinely mis-encoded file looks like. (An
        # en-dash cannot serve here: latin-1 has no such character to mis-encode.)
        path = self._write(_LATIN1_SCENARIO, encoding="latin-1")
        with self.assertRaises(ValueError) as caught:
            self.parser.parse_file(path, False)
        message = str(caught.exception)
        self.assertIn(f"{path}:4:", message)   # the comment line, not a byte offset
        self.assertIn("UTF-8", message)
