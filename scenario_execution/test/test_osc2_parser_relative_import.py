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
"""A relative string import resolves against the directory of the file that contains it."""

import os

import pytest

from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.model.types import EnumDeclaration

from .common import DebugLogger


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture(name="tree")
def _tree(tmp_path):
    """scenarios/entry.osc -> ../libs/a.osc -> nested/b.osc, and a directory unrelated to all three."""
    _write(tmp_path / "libs" / "nested" / "b.osc", "enum b_enum: [b_one, b_two]\n")
    _write(tmp_path / "libs" / "a.osc", 'import "nested/b.osc"\n\nenum a_enum: [a_one, a_two]\n')
    entry = _write(tmp_path / "scenarios" / "entry.osc", """\
import "../libs/a.osc"

scenario test_relative:
    do serial:
        wait elapsed(1s)
""")
    (tmp_path / "elsewhere").mkdir()
    return tmp_path, entry


def _enums(file):
    parser = OpenScenario2Parser(DebugLogger(""))
    model = parser.load_internal_model(parser.parse_file(file), file)
    return sorted(enum.name for enum in model.find_children_of_type(EnumDeclaration))


@pytest.mark.parametrize("cwd", ["", "scenarios", "libs", "elsewhere"])
def test_nested_imports_ignore_cwd(tree, monkeypatch, cwd):
    root, entry = tree
    monkeypatch.chdir(root / cwd)
    assert _enums(str(entry)) == ["a_enum", "b_enum"]


def test_entry_file_given_relative_to_cwd(tree, monkeypatch):
    root, entry = tree
    monkeypatch.chdir(root / "elsewhere")
    assert _enums(os.path.relpath(entry)) == ["a_enum", "b_enum"]


def test_absolute_import_is_used_as_written(tree, monkeypatch):
    root, _ = tree
    entry = _write(root / "scenarios" / "absolute.osc", f'import "{root / "libs" / "a.osc"}"\n')
    monkeypatch.chdir(root / "elsewhere")
    assert _enums(str(entry)) == ["a_enum", "b_enum"]


def test_missing_import_names_resolved_path(tree, monkeypatch):
    root, _ = tree
    entry = _write(root / "scenarios" / "missing.osc", 'import "../libs/missing.osc"\n')
    monkeypatch.chdir(root / "elsewhere")
    with pytest.raises(ValueError, match=str(root / "libs" / "missing.osc")):
        _enums(str(entry))
