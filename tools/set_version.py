#!/usr/bin/env python3
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

"""Set the version across every source ``package.xml`` and ``setup.py`` in the workspace.

Usage::

    set_version.py X.Y.Z              # set an explicit version
    set_version.py major|minor|patch  # bump relative to the current version

The current version is read from the canonical ``scenario_execution/package.xml``.
Generated/vendored trees (install, build, venvs) are skipped.
"""

import os
import re
import sys

SKIP_DIRS = {"install", "build", "venv", "vvenv", ".pypi_venv", ".git", "__pycache__"}
CANONICAL = os.path.join("scenario_execution", "package.xml")


def current_version() -> str:
    try:
        text = open(CANONICAL, encoding="utf-8").read()
    except OSError as e:
        sys.exit(f"Could not read {CANONICAL}: {e}")
    m = re.search(r"<version>([^<]+)</version>", text)
    if not m:
        sys.exit(f"No <version> found in {CANONICAL}")
    return m.group(1)


def resolve(arg: str, cur: str) -> str:
    if re.fullmatch(r"\d+\.\d+\.\d+", arg):
        return arg
    if arg in ("major", "minor", "patch"):
        major, minor, patch = (int(x) for x in cur.split("."))
        if arg == "major":
            return f"{major + 1}.0.0"
        if arg == "minor":
            return f"{major}.{minor + 1}.0"
        return f"{major}.{minor}.{patch + 1}"
    sys.exit("Version must be 'X.Y.Z' or one of: major, minor, patch")


def iter_files(name: str):
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if name in files:
            yield os.path.join(root, name)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    cur = current_version()
    new = resolve(sys.argv[1], cur)

    changed = []
    for f in iter_files("package.xml"):
        s = open(f, encoding="utf-8").read()
        n = re.sub(r"<version>[^<]+</version>", f"<version>{new}</version>", s, count=1)
        if n != s:
            open(f, "w", encoding="utf-8").write(n)
            changed.append(f)
    for f in iter_files("setup.py"):
        s = open(f, encoding="utf-8").read()
        n = re.sub(r"(\bversion\s*=\s*)(['\"])[^'\"]+\2", rf"\g<1>\g<2>{new}\g<2>", s, count=1)
        if n != s:
            open(f, "w", encoding="utf-8").write(n)
            changed.append(f)

    print(f"Set version {cur} -> {new} ({len(changed)} file(s) updated)")
    if cur == new:
        print("(no changes; already at that version)")


if __name__ == "__main__":
    main()
