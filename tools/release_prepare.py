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

"""Prepare a release: changelogs, their headings, and the version, in one step.

Usage::

    release_prepare.py X.Y.Z              # the next version, explicitly
    release_prepare.py major|minor|patch  # bumped from the current one
    release_prepare.py --list             # which packages a release touches, and which never

A release touches only the packages that are released: those whose ``package.xml`` carries the
current version. Every other package in the workspace -- the examples, the ``*_test`` packages,
the simulation helpers, the tools, the libraries kept out of the ROS build farm -- is fixed at
``0.0.0`` and is not a version this script will ever write. That is what keeps a release to the
files that have to change, and it is checked: a package at any third version is refused.

For each released package, in order:

1. the ``Forthcoming`` section of its ``CHANGELOG.rst`` is filled from the git history since the
   last version tag (``catkin_pkg``'s generator, over the released packages alone -- the CLI
   ``catkin_generate_changelog`` would create changelogs for the packages that have none);
2. that heading becomes ``X.Y.Z (today)``;
3. ``<version>`` in its ``package.xml`` becomes ``X.Y.Z``. Nothing else carries a version:
   every ``setup.py`` reads its ``package.xml``.

The result is a working tree to review and commit; the tag is pushed after the merge, by the
release gate. ``catkin_prepare_release`` does not apply to this repository -- it requires a
literal ``version='X.Y.Z'`` in every ``setup.py``.
"""

import datetime
import os
import re
import subprocess  # nosec B404
import sys

from catkin_pkg.changelog import CHANGELOG_FILENAME
from catkin_pkg.changelog_generator import get_forthcoming_changes, update_changelogs
from catkin_pkg.changelog_generator_vcs import get_vcs_client
from catkin_pkg.package_version import get_forthcoming_label, rename_section
from catkin_pkg.packages import find_packages

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANONICAL = os.path.join("scenario_execution", "package.xml")
UNRELEASED = "0.0.0"
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def read_version(package_xml):
    with open(package_xml, encoding="utf-8") as f:
        match = re.search(r"<version>\s*([^<\s]+)\s*</version>", f.read())
    if not match:
        sys.exit(f"No <version> in {package_xml}")
    return match.group(1)


def resolve(arg, current):
    if VERSION_PATTERN.match(arg):
        return arg
    if arg in ("major", "minor", "patch"):
        major, minor, patch = (int(x) for x in current.split("."))
        return {"major": f"{major + 1}.0.0",
                "minor": f"{major}.{minor + 1}.0",
                "patch": f"{major}.{minor}.{patch + 1}"}[arg]
    sys.exit("Version must be X.Y.Z or one of: major, minor, patch")


def partition(packages, current):
    """The released packages and the fixed ones; anything else is an error."""
    released, fixed, other = {}, {}, {}
    for path, package in packages.items():
        version = package.version
        if version == current:
            released[path] = package
        elif version == UNRELEASED:
            fixed[path] = package
        else:
            other[path] = version
    if other:
        sys.exit("A package is at neither the release version nor 0.0.0:\n"
                 + "\n".join(f"  {p}: {v}" for p, v in sorted(other.items())))
    return released, fixed


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__.strip().splitlines()[0] + "\n\nusage: release_prepare.py X.Y.Z | major | minor | patch | --list")
    os.chdir(ROOT)
    current = read_version(CANONICAL)
    packages = find_packages(".")
    released, fixed = partition(packages, current)

    if sys.argv[1] == "--list":
        print(f"Released with the next version (now {current}):")
        for path in sorted(released):
            print(f"  + {released[path].name}  ({path})")
        print(f"Fixed at {UNRELEASED}, never released:")
        for path in sorted(fixed):
            print(f"  - {fixed[path].name}  ({path})")
        return 0

    version = resolve(sys.argv[1], current)
    if version == current:
        sys.exit(f"{version} is the current version already")

    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True).stdout
    if dirty:
        sys.exit("The working tree is not clean; a release is prepared on top of a commit, alone:\n" + dirty)
    vcs = get_vcs_client(".")
    latest_tag = vcs.get_latest_tag_name()
    if not VERSION_PATTERN.match(latest_tag):
        sys.exit(f"The latest tag is {latest_tag!r}, not X.Y.Z; the changelog generator would refuse it")

    without_changelog = [p for p in released if not os.path.exists(os.path.join(p, CHANGELOG_FILENAME))]
    if without_changelog:
        sys.exit("A released package has no CHANGELOG.rst; add one before releasing:\n"
                 + "\n".join(f"  {p}" for p in without_changelog))

    # 1. Forthcoming entries from the history since the last tag, released packages only. One
    #    line per commit: its subject. The body is what git is for, and a changelog of pasted
    #    paragraphs is one nobody reads.
    changes = get_forthcoming_changes(vcs)
    for entries in changes.values():
        for entry in entries or ():
            entry.msg = entry.msg.strip().splitlines()[0] if entry.msg.strip() else entry.msg
    update_changelogs(".", released, changes, vcs_client=vcs)

    # 2. The heading. The generator only adds a Forthcoming section where there are entries, so a
    #    package with no change since the last tag keeps whatever heading it had -- an empty
    #    Forthcoming, which becomes an empty version section: released, unchanged.
    label = f"{version} ({datetime.date.today().isoformat()})"
    for path in released:
        changelog = os.path.join(path, CHANGELOG_FILENAME)
        with open(changelog, encoding="utf-8") as f:
            data = f.read()
        forthcoming = get_forthcoming_label(data)
        if not forthcoming:
            sys.exit(f"{changelog} has no Forthcoming section to name {version}; add an empty one")
        with open(changelog, "w", encoding="utf-8") as f:
            f.write(rename_section(data, forthcoming, label))

    # 3. The version, in the one file per package that carries it.
    for path in released:
        package_xml = os.path.join(path, "package.xml")
        with open(package_xml, encoding="utf-8") as f:
            data = f.read()
        data, count = re.subn(r"<version>\s*[^<\s]+\s*</version>", f"<version>{version}</version>", data, count=1)
        if count != 1:
            sys.exit(f"Could not set the version in {package_xml}")
        with open(package_xml, "w", encoding="utf-8") as f:
            f.write(data)

    print(f"Prepared {version} from {current}: {len(released)} packages, their changelogs and versions.")
    print("Review the diff, then commit and open the release pull request:")
    print(f'  git switch -c release-{version} && git commit -am "Release {version}" && git push -u origin release-{version}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
