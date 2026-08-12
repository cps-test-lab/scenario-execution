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

"""Minimal tests for the JSON introspection entry points."""

import os
import tempfile
import unittest

from scenario_execution.introspection import (_parse_osc_library,
                                               _syntax_diagnostics, list_actions,
                                               validate)


class TestParseOscLibrary(unittest.TestCase):
    """The .osc-source parser is pure and environment-independent."""

    def test_declaration_doc_and_parameters(self):
        # The block doc is the comment(s) between the declaration line and the
        # first parameter; per-parameter docs come from trailing inline comments.
        text = (
            "action my_action:\n"
            "    # Log a message.\n"
            "    msg: string = \"hi\"  # the message to log\n"
            "    level: string\n"
        )
        decls = _parse_osc_library(text, "helpers")
        self.assertEqual(len(decls), 1)
        decl = decls[0]
        self.assertEqual(decl["name"], "my_action")
        self.assertEqual(decl["kind"], "action")
        self.assertEqual(decl["source_lib"], "helpers")
        self.assertEqual(decl["doc"], "Log a message.")
        self.assertEqual(len(decl["parameters"]), 2)
        msg = decl["parameters"][0]
        self.assertEqual(msg["name"], "msg")
        self.assertEqual(msg["type"], "string")
        self.assertEqual(msg["default"], '"hi"')
        self.assertEqual(msg["doc"], "the message to log")
        # A parameter with no default / no comment reports None, not "".
        self.assertIsNone(decl["parameters"][1]["default"])

    def test_multiple_kinds_separated(self):
        text = "actor base\n\nstruct point:\n    x: float\n"
        kinds = {d["kind"]: d["name"] for d in _parse_osc_library(text, "lib")}
        self.assertEqual(kinds, {"actor": "base", "struct": "point"})


class TestSyntaxDiagnostics(unittest.TestCase):

    def test_line_column_extracted(self):
        diags = _syntax_diagnostics("line 4:7 mismatched input 'x'", "f.osc")
        self.assertEqual(len(diags), 1)
        self.assertEqual((diags[0]["line"], diags[0]["column"]), (4, 7))
        self.assertEqual(diags[0]["phase"], "syntax")
        self.assertIn("mismatched input", diags[0]["message"])

    def test_unparseable_message_still_reported(self):
        diags = _syntax_diagnostics("some opaque failure", "f.osc")
        self.assertEqual(len(diags), 1)
        self.assertIsNone(diags[0]["line"])
        self.assertEqual(diags[0]["message"], "some opaque failure")


class TestValidate(unittest.TestCase):

    def _write(self, content):
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".osc", delete=False, encoding="utf-8")
        handle.write(content)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_missing_file(self):
        report = validate("/no/such/file.osc")
        self.assertFalse(report["valid"])
        self.assertIn("not found", report["diagnostics"][0]["message"])

    def test_valid_syntax_level(self):
        path = self._write("import osc.helpers\n\nscenario test:\n    timeout(10s)\n")
        report = validate(path, level="syntax")
        self.assertTrue(report["valid"], report["diagnostics"])
        self.assertEqual(report["diagnostics"], [])

    def test_syntax_error_has_location(self):
        # 'do serial' without the trailing ':' is a parse error.
        path = self._write(
            "import osc.helpers\n\nscenario test:\n    do serial\n        log()\n")
        report = validate(path, level="syntax")
        self.assertFalse(report["valid"])
        self.assertTrue(report["diagnostics"])
        self.assertTrue(all(d["phase"] == "syntax" for d in report["diagnostics"]))
        self.assertTrue(any(d["line"] is not None for d in report["diagnostics"]))

    def test_unknown_action_is_semantic(self):
        path = self._write(
            "import osc.helpers\n\nscenario test:\n    do totally_unknown_action()\n")
        report = validate(path)  # full
        self.assertFalse(report["valid"])
        diag = report["diagnostics"][0]
        self.assertEqual(diag["phase"], "semantic")
        self.assertEqual(diag["line"], 4)
        self.assertIn("totally_unknown_action", diag["message"])


class TestListActions(unittest.TestCase):
    """Light integration: reflects whatever is installed in this environment,
    which always includes the base ``osc.helpers`` library."""

    def test_buckets_and_helpers_log_action(self):
        catalog = list_actions()
        self.assertEqual(
            set(catalog), {"actions", "modifiers", "actors", "structs"})
        log = next((a for a in catalog["actions"] if a["name"] == "log"), None)
        self.assertIsNotNone(log, "expected the 'log' action from osc.helpers")
        # 'log' is backed by an installed action entry point.
        self.assertTrue(log["resolvable"])
        self.assertEqual(log["kind"], "action")

    def test_builtin_modifiers_resolvable(self):
        catalog = list_actions()
        mods = {m["name"]: m["resolvable"] for m in catalog["modifiers"]}
        self.assertIn("timeout", mods)
        self.assertTrue(mods["timeout"])  # a hard-coded built-in modifier

    def test_each_bucket_sorted_by_name(self):
        for bucket in list_actions().values():
            names = [d["name"] for d in bucket]
            self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()
