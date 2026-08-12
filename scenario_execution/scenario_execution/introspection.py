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

"""Programmatic, JSON-friendly introspection of the OpenSCENARIO 2 DSL.

Two public entry points, both returning plain data structures (no exceptions,
no ANSI-coloured logging on stdout) so they can be consumed by tools and LLMs:

* :func:`validate` — parse + semantically resolve a ``.osc`` file and return a
  structured list of diagnostics (line/column/message) instead of raising.
* :func:`list_actions` — enumerate the actions/modifiers/actors/structs that are
  available in the *current environment* (which depends on the installed
  ``scenario_execution.actions`` / ``scenario_execution.osc_libraries`` packages),
  together with their osc signatures and inline documentation.

Both are also runnable as a module so they can be executed inside a runtime
container image and have their JSON output parsed by a caller on the host::

    python -m scenario_execution.introspection validate <file.osc>
    python -m scenario_execution.introspection list-actions
"""

import argparse
import json
import os
import re
import sys
from importlib.metadata import entry_points
from importlib.resources import files

from scenario_execution.utils.logging import BaseLogger

# Built-in modifiers are hard-coded decorators in model_to_py_tree.py rather than
# entry points, so they must be listed explicitly to be reported as resolvable.
BUILTIN_MODIFIERS = [
    "repeat", "inverter", "timeout", "retry",
    "failure_is_running", "failure_is_success",
    "running_is_failure", "running_is_success",
    "success_is_failure", "success_is_running",
]


class _StderrLogger(BaseLogger):
    """Logger that never writes to stdout (keeps JSON output clean)."""

    def info(self, msg: str) -> None:
        print(f'[scenario_execution] [INFO] {msg}', file=sys.stderr)

    def debug(self, msg: str) -> None:
        if self.log_debug:
            print(f'[scenario_execution] [DEBUG] {msg}', file=sys.stderr)

    def warning(self, msg: str) -> None:
        print(f'[scenario_execution] [WARN] {msg}', file=sys.stderr)

    def error(self, msg: str) -> None:
        print(f'[scenario_execution] [ERROR] {msg}', file=sys.stderr)


# ── Validation ──────────────────────────────────────────────────────────────

_SYNTAX_RE = re.compile(r"line (\d+):(\d+)\s+(.*)")
# Semantic errors that get wrapped into a plain ValueError still embed their
# location as "(line: L, column: C ...)" in the message text.
_CTX_RE = re.compile(r"line:\s*(\d+),\s*column:\s*(\d+)")


def _extract_ctx(message):
    match = _CTX_RE.search(str(message))
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def _diagnostic(message, line=None, column=None, file=None, phase="semantic"):
    return {"severity": "error", "line": line, "column": column,
            "message": message, "file": file, "phase": phase}


def _syntax_diagnostics(message, file):
    """Split the newline-joined syntax-error message into per-line diagnostics."""
    diagnostics = []
    for raw in str(message).splitlines():
        raw = raw.strip()
        if not raw:
            continue
        match = _SYNTAX_RE.search(raw)
        if match:
            diagnostics.append(_diagnostic(
                match.group(3).strip(), line=int(match.group(1)),
                column=int(match.group(2)), file=file, phase="syntax"))
        else:
            diagnostics.append(_diagnostic(raw, file=file, phase="syntax"))
    if not diagnostics:
        diagnostics.append(_diagnostic(str(message), file=file, phase="syntax"))
    return diagnostics


def validate(file_path, level="full", debug=False):  # pylint: disable=too-many-return-statements
    """Validate an OpenSCENARIO 2 ``.osc`` file, returning structured diagnostics.

    Runs the same pipeline the engine uses at launch — ANTLR parse (syntax) plus
    internal-model build and semantic resolution (type checks, import/library
    resolution, action-plugin resolution) — but catches the errors and reports
    them instead of raising.

    ``level`` controls how far to go:

    * ``"syntax"`` — ANTLR parse only. Environment-independent, so safe to run
      anywhere (e.g. at submit time on a host that lacks the ROS action packages).
    * ``"full"`` (default) — also build the model and create the py-tree, which is
      where action/plugin resolution happens. Action/library resolution only
      succeeds for packages installed in *this* environment; run inside the
      runtime image to validate scenarios that use ROS/nav2/gazebo actions,
      otherwise their actions will be falsely reported as unknown.

    Note: semantic resolution aborts on the *first* error (engine limitation), so
    a valid-syntax file reports at most one semantic diagnostic per run. Syntax
    errors, however, are aggregated.

    Returns ``{"valid": bool, "diagnostics": [<diagnostic>, ...]}`` where each
    diagnostic is ``{severity, line, column, message, file, phase}`` and ``phase``
    is ``"syntax"`` or ``"semantic"``.
    """
    # Imported lazily: importing the parser pulls in py_trees and the whole model
    # stack, which is unnecessary for list_actions and slow to import.
    # pylint: disable=import-outside-toplevel
    from scenario_execution.model.error import OSC2Error
    from scenario_execution.model.osc2_parser import OpenScenario2Parser
    # pylint: enable=import-outside-toplevel

    logger = _StderrLogger('scenario_execution', debug)
    parser = OpenScenario2Parser(logger)

    if not os.path.isfile(file_path):
        return {"valid": False,
                "diagnostics": [_diagnostic(f"scenario file not found: {file_path}",
                                            file=file_path, phase="syntax")]}

    # Phase 1: syntax (ANTLR parse). Raises ValueError with newline-joined
    # "line L:C msg" entries.
    try:
        parser.parse_file(file_path)
    except ValueError as e:
        return {"valid": False, "diagnostics": _syntax_diagnostics(e, file_path)}
    except Exception as e:  # pylint: disable=broad-except  # report, never raise
        return {"valid": False,
                "diagnostics": [_diagnostic(str(e), file=file_path, phase="syntax")]}

    if level == "syntax":
        return {"valid": True, "diagnostics": []}

    # Phase 2: full model build + semantic resolution + py-tree creation. The
    # latter is where action/plugin resolution happens (name lookup, BaseAction
    # subclass check, osc-vs-__init__/execute signature match), so we run the
    # whole pipeline to catch those. OSC2Error carries an osc_ctx
    # (line, column, text, file); ModelBuilder wraps some into ValueError.
    try:
        parser.process_file(file_path)
    except OSC2Error as e:
        line = column = None
        ctx_file = file_path
        if e.osc_ctx and len(e.osc_ctx) == 4:
            line, column, _text, ctx_file = e.osc_ctx
        return {"valid": False,
                "diagnostics": [_diagnostic(e.msg, line=line, column=column,
                                            file=ctx_file or file_path,
                                            phase="semantic")]}
    except Exception as e:  # pylint: disable=broad-except  # report, never raise
        line, column = _extract_ctx(e)
        return {"valid": False,
                "diagnostics": [_diagnostic(str(e), line=line, column=column,
                                            file=file_path, phase="semantic")]}

    return {"valid": True, "diagnostics": []}


# ── Action / declaration catalog ──────────────────────────────────────────────

# A top-level declaration begins in column 0. We capture the kinds an LLM needs
# to know to author scenarios.
_DECL_RE = re.compile(
    r"^(action|modifier|actor|struct|scenario|enum|global)\s+([A-Za-z_]\w*)")
# An indented parameter line: "name: type [= default] [# comment]".
_PARAM_RE = re.compile(
    r"^\s+([A-Za-z_]\w*)\s*:\s*([^=#]+?)\s*(?:=\s*(.+?))?\s*(?:#\s*(.*))?$")
_COMMENT_RE = re.compile(r"^\s*#\s?(.*)$")


def _parse_osc_library(text, source_lib):
    """Extract top-level declarations (with docs + signatures) from .osc source."""
    lines = text.splitlines()
    declarations = []
    i = 0
    n = len(lines)
    while i < n:
        match = _DECL_RE.match(lines[i])
        if not match:
            i += 1
            continue
        kind, name = match.group(1), match.group(2)
        start = i
        i += 1
        # The block extends until the next column-0 non-blank, non-comment line.
        block_end = i
        while block_end < n:
            line = lines[block_end]
            if line.strip() and not line[0].isspace() and not line.lstrip().startswith("#"):
                break
            block_end += 1
        block = lines[start:block_end]

        doc_parts = []
        params = []
        pending_doc = []
        for line in block[1:]:
            comment = _COMMENT_RE.match(line)
            if comment:
                # A full-line comment: block doc if no params yet, else attaches
                # to the next parameter.
                if params or pending_doc or _PARAM_RE.match(line):
                    pending_doc.append(comment.group(1).strip())
                else:
                    doc_parts.append(comment.group(1).strip())
                continue
            pmatch = _PARAM_RE.match(line)
            if pmatch:
                pname, ptype, pdefault, pcomment = pmatch.groups()
                param_doc = pcomment.strip() if pcomment else " ".join(pending_doc)
                params.append({
                    "name": pname,
                    "type": ptype.strip(),
                    "default": pdefault.strip() if pdefault else None,
                    "doc": param_doc or None,
                })
                pending_doc = []
        declarations.append({
            "name": name,
            "kind": kind,
            "source_lib": source_lib,
            "doc": " ".join(doc_parts).strip() or None,
            "parameters": params,
            "raw": "\n".join(block).rstrip(),
        })
        i = block_end
    return declarations


def _osc_library_files():
    """Yield (library_name, path) for every registered scenario_execution osc library."""
    for ep in entry_points(group='scenario_execution.osc_libraries'):
        try:
            resource, filename = ep.load()()
            path = str(files(resource).joinpath('lib_osc', filename))
            if os.path.isfile(path):
                yield ep.name, path
        except Exception:  # pylint: disable=broad-except  # one broken library must not sink the rest
            continue


def list_actions():
    """Enumerate the DSL vocabulary available in the current environment.

    Unions three sources: the ``scenario_execution.actions`` entry points (which
    action *names* resolve to a Python plugin), the built-in modifiers, and the
    declarations (with osc signatures + inline docs) parsed from every registered
    ``scenario_execution.osc_libraries`` ``.osc`` file.

    Because entry points are environment-specific, the result reflects whatever is
    installed here — run inside the runtime image to see the full ROS/nav2/gazebo
    action set.

    Returns ``{"actions": [...], "modifiers": [...], "actors": [...],
    "structs": [...]}``. Each declaration is ``{name, kind, source_lib, doc,
    parameters:[{name,type,default,doc}], raw, resolvable}`` where ``resolvable``
    marks entries backed by an installed Python plugin (actions/modifiers).
    """
    action_eps = {ep.name for ep in entry_points(group='scenario_execution.actions')}
    modifier_eps = {ep.name for ep in entry_points(group='scenario_execution.modifiers')}
    resolvable_modifiers = set(BUILTIN_MODIFIERS) | modifier_eps

    catalog = {"actions": [], "modifiers": [], "actors": [], "structs": []}
    seen = set()
    for library_name, path in _osc_library_files():
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        for decl in _parse_osc_library(text, library_name):
            key = (decl["kind"], decl["name"])
            if key in seen:
                continue
            seen.add(key)
            if decl["kind"] == "action":
                decl["resolvable"] = decl["name"] in action_eps
                catalog["actions"].append(decl)
            elif decl["kind"] == "modifier":
                decl["resolvable"] = decl["name"] in resolvable_modifiers
                catalog["modifiers"].append(decl)
            elif decl["kind"] == "actor":
                catalog["actors"].append(decl)
            elif decl["kind"] == "struct":
                catalog["structs"].append(decl)

    # Surface action plugins that are registered but have no .osc declaration in a
    # reachable library (so the caller still learns the name exists).
    declared_actions = {a["name"] for a in catalog["actions"]}
    for name in sorted(action_eps - declared_actions):
        catalog["actions"].append({
            "name": name, "kind": "action", "source_lib": None,
            "doc": None, "parameters": [], "raw": None, "resolvable": True,
        })
    for bucket in catalog.values():
        bucket.sort(key=lambda d: d["name"])
    return catalog


# ── Module CLI (python -m scenario_execution.introspection <subcommand>) ──────

def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m scenario_execution.introspection",
        description="JSON introspection of the OpenSCENARIO 2 DSL.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_validate = sub.add_parser(
        "validate", help="Validate a .osc file, emitting JSON diagnostics.")
    p_validate.add_argument("file", help="Path to the .osc scenario file")
    p_validate.add_argument("--level", choices=["syntax", "full"], default="full",
                            help="'syntax' = parse only (environment-independent); "
                                 "'full' = also resolve actions (default)")
    p_validate.add_argument("--debug", action="store_true",
                            help="Verbose logging to stderr")

    sub.add_parser(
        "list-actions",
        help="List the DSL vocabulary available in this environment, as JSON.")

    args = parser.parse_args(argv)
    if args.command == "validate":
        result = validate(args.file, level=args.level, debug=args.debug)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["valid"] else 1)
    else:  # list-actions
        print(json.dumps(list_actions(), indent=2))


if __name__ == "__main__":
    main()
