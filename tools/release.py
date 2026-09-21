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

"""Release scenario-execution: a candidate tried by hand first, the real tag only after.

Usage::

    release.py rc    X.Y.Z [--commit SHA]   # 1.6.0rcN to TestPyPI, and the bloom rehearsal
    release.py final X.Y.Z [--commit SHA]   # X.Y.Z and <distro>-X.Y.Z tags -> PyPI, the GitHub
                                            # Release; then bloom
    release.py github-release X.Y.Z         # the GitHub Release alone, for an existing tag

A release has two halves: the ``scenario-execution`` wheel, which the publish workflow uploads
from the ``X.Y.Z`` tag, and the ROS packages, which bloom takes to each distro's build farm from
a ``<distro>-X.Y.Z`` tag beside it -- one per supported distro, all on the same commit, since
the same source builds on every one of them. Neither can be taken back -- an upload can be yanked, never
replaced, and a tag is never moved -- so both are tried first: the wheel as a release
candidate on TestPyPI, and bloom as a rehearsal that does everything but push.

Every step works from a clean clone of the exact commit, never this checkout, which may hold
work of its own. The gates, each refusing on its own:

1. the commit is on ``origin/main`` (a tag names a commit every clone can reach);
2. the workflows that test the repository are green on it (``gh run list --commit``);
3. ``scenario_execution/package.xml`` says ``X.Y.Z`` -- otherwise the release is not prepared
   (``make release-prepare``), and a tag that disagrees with the tree would fail its build
   after it exists;
4. every ``package.xml`` is at ``X.Y.Z`` or at ``0.0.0``, and for each distro the ``0.0.0`` set is
   what the release repository's ``<distro>.ignored`` names, and that distro has a bloom track:
   bloom drops the ignored packages, then insists the rest share one version, so a package in
   neither is released by accident or fails the check;
5. ``final`` only: a candidate of ``X.Y.Z`` is on TestPyPI, and the tag does not exist yet.

Needs ``gh`` (logged in) and, for the rehearsal, network access to the release repository.
"""

import argparse
import json
import os
import re
import subprocess  # nosec B404
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLONES = ROOT / "build" / "release"

REPO = "cps-test-lab/scenario-execution"
DISTRIBUTION = "scenario-execution"
PACKAGE_XML = "scenario_execution/package.xml"
UNRELEASED = "0.0.0"
#: Workflows that must be green on the commit, by their ``name:``.
REQUIRED_WORKFLOWS = ("test-build", "Scan")

#: Every distro main is released for; each has a track in the release repository.
ROS_DISTROS = ("jazzy", "lyrical")
ROSDISTRO_KEY = "scenario_execution"
RELEASE_REPOSITORY = "https://github.com/ros2-gbp/scenario_execution-release.git"
RELEASE_REPOSITORY_RAW = "https://raw.githubusercontent.com/ros2-gbp/scenario_execution-release/master"
ROSDEP_SOURCES_URL = "https://raw.githubusercontent.com/ros/rosdistro/master/rosdep/sources.list.d/20-default.list"

VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def run(*cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()  # nosec B603


def fail(message):
    print(f"FAIL  {message}")
    return 1


def ok(message):
    print(f"ok    {message}")


# -- the clone ----------------------------------------------------------------------------

def resolve_commit(commit):
    """The full sha, on origin/main, after a fetch."""
    run("git", "fetch", "-q", "origin", "main", "--tags", cwd=ROOT)
    sha = run("git", "rev-parse", commit or "origin/main", cwd=ROOT)
    on_main = subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"],  # nosec B603 B607
                             cwd=ROOT, check=False).returncode == 0
    if not on_main:
        raise SystemExit(fail(f"{sha[:8]} is not on origin/main; a release names a commit every clone can reach"))
    ok(f"{sha[:8]} is on origin/main")
    return sha


def clean_clone(sha):
    """A fresh checkout of exactly that commit, with the public remote as origin."""
    remote = run("git", "remote", "get-url", "origin", cwd=ROOT)
    target = CLONES / sha[:12]
    if target.exists():
        subprocess.run(["rm", "-rf", str(target)], check=True)  # nosec B603 B607
    CLONES.mkdir(parents=True, exist_ok=True)
    run("git", "clone", "-q", "--no-checkout", "--reference-if-able", str(ROOT), remote, str(target))
    run("git", "checkout", "-q", sha, cwd=target)
    ok(f"clean clone at {target.relative_to(ROOT)}")
    return target


# -- the gates ----------------------------------------------------------------------------

def ci_green(sha):
    runs = json.loads(run("gh", "run", "list", "-R", REPO, "--commit", sha, "--json", "workflowName,conclusion,status"))
    green = {r["workflowName"] for r in runs if r["conclusion"] == "success"}
    missing = [w for w in REQUIRED_WORKFLOWS if w not in green]
    if missing:
        seen = {r["workflowName"]: r["conclusion"] or r["status"] for r in runs}
        return not fail(f"not green on {sha[:8]}: {', '.join(missing)}  (runs: {seen})")
    ok(f"CI green on {sha[:8]}: {', '.join(REQUIRED_WORKFLOWS)}")
    return True


def package_xml_field(path, field):
    match = re.search(rf"<{field}>\s*([^<\s]+)\s*</{field}>", path.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit(fail(f"{path} carries no <{field}>"))
    return match.group(1)


def fetch_text(url):
    with urllib.request.urlopen(url, timeout=30) as response:  # nosec B310
        return response.read().decode()


def tree_agrees(clone, version):
    """The tree says VERSION, and every package is at VERSION or at 0.0.0 and ignored by bloom."""
    in_tree = package_xml_field(clone / PACKAGE_XML, "version")
    if in_tree != version:
        return not fail(f"{PACKAGE_XML} says {in_tree}, releasing {version}: prepare the release first "
                        f"(make release-prepare VERSION={version})")
    ok(f"{PACKAGE_XML} says {version}")

    released, fixed, other = set(), set(), {}
    for path in sorted(clone.rglob("package.xml")):
        name, found = package_xml_field(path, "name"), package_xml_field(path, "version")
        if found == version:
            released.add(name)
        elif found == UNRELEASED:
            fixed.add(name)
        else:
            other[name] = found
    if other:
        return not fail("a package is at neither the release version nor 0.0.0: "
                        + ", ".join(f"{n} ({v})" for n, v in sorted(other.items())))
    tracks = fetch_text(f"{RELEASE_REPOSITORY_RAW}/tracks.yaml")
    for distro in ROS_DISTROS:
        if not re.search(rf"(?m)^  {distro}:$", tracks):
            # Not `bloom-release --new-track`: it goes on to release the version on main, whose
            # `<distro>-<version>` tag does not exist before this distro's first release.
            return not fail(f"the release repository has no {distro} track; create it once, in a clone of "
                            f"{RELEASE_REPOSITORY} on master: `git-bloom-config copy {ROS_DISTROS[0]} {distro}`, "
                            f"then `git-bloom-config edit {distro}` answering ROS Distro `{distro}` and "
                            f"Release Tag `{distro}-:{{version}}` (keep the rest), then `git push origin master`")
        try:
            ignored = set(fetch_text(f"{RELEASE_REPOSITORY_RAW}/{distro}.ignored").split())
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            ignored = set()
        unignored = fixed - ignored
        if unignored:
            return not fail(f"at 0.0.0 but not in the release repository's {distro}.ignored, so bloom would "
                            f"release or refuse them: {', '.join(sorted(unignored))} -- add them there first "
                            f"({RELEASE_REPOSITORY})")
        stale = ignored & released
        if stale:
            return not fail(f"in {distro}.ignored but at the release version: {', '.join(sorted(stale))}")
    ok(f"{len(released)} packages at {version}, {len(fixed)} at {UNRELEASED} and ignored by bloom "
       f"on {', '.join(ROS_DISTROS)}")
    return True


def testpypi_versions():
    try:
        return set(json.loads(fetch_text(f"https://test.pypi.org/pypi/{DISTRIBUTION}/json"))["releases"])
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return set()
        raise


def next_rc(version):
    numbers = [int(m.group(1)) for v in testpypi_versions() if (m := re.fullmatch(rf"{re.escape(version)}rc(\d+)", v))]
    return max(numbers, default=0) + 1


def rc_exists(version):
    if not any(v.startswith(f"{version}rc") for v in testpypi_versions()):
        return not fail(f"no candidate of {version} on TestPyPI -- run `make release-rc VERSION={version}` "
                        "and test it by hand first")
    ok(f"a candidate of {version} is on TestPyPI")
    return True


def gate(version, commit):
    sha = resolve_commit(commit)
    clone = clean_clone(sha)
    if not ci_green(sha) or not tree_agrees(clone, version):
        return None
    return sha, clone


# -- the bloom rehearsal ------------------------------------------------------------------

def lay_out_bloom_rehearsal(clone, version):
    """Everything `bloom-release --pretend` needs, so that one pasted line runs it.

    A clone of the release repository with every branch local and its track pointed at the
    clean clone; the clone given a `main` branch and the two tags bloom looks for, locally
    only; bloom and rosdep in an environment of their own (lay_out_bloom_environment). `--pretend`
    does the whole release -- export at the tag, import, the version check after the ignore
    list, every release and debian branch with every rosdep key resolved -- and dry-runs the
    pushes.
    """
    root = CLONES / f"bloom-rehearsal-{version}"
    if root.exists():
        subprocess.run(["rm", "-rf", str(root)], check=True)  # nosec B603 B607
    root.mkdir(parents=True)
    release_repo = root / "release-repository"
    run("git", "clone", "-q", RELEASE_REPOSITORY, str(release_repo))
    # bloom clones this again, and a clone carries only local branches: every release/ and
    # debian/ branch it builds on has to be one here.
    local = set(run("git", "branch", "--format=%(refname:short)", cwd=release_repo).split())
    for ref in run("git", "branch", "-r", cwd=release_repo).split():
        name = ref.removeprefix("origin/")
        if ref.startswith("origin/") and not ref.startswith("origin/HEAD") and name not in local:
            run("git", "branch", "--track", name, ref, cwd=release_repo)

    run("git", "branch", "-f", "main", "HEAD", cwd=clone)
    for tag in release_tags(version):
        run("git", "tag", "-f", tag, cwd=clone)
    tracks = release_repo / "tracks.yaml"
    text, count = re.subn(r"(?m)^(\s*vcs_uri:\s*).*$", lambda m: m.group(1) + str(clone), tracks.read_text(encoding="utf-8"))
    if count == 0:
        raise SystemExit(fail(f"{tracks} names no vcs_uri to point at the clone"))
    tracks.write_text(text, encoding="utf-8")
    run("git", "commit", "-q", "-am", "rehearsal: the upstream is the local clone", cwd=release_repo)

    lay_out_bloom_environment(root)
    ok(f"bloom rehearsal laid out at {root.relative_to(ROOT)}")
    return root


def lay_out_bloom_environment(root):
    """bloom and rosdep of their own under ``root``: a venv, the default rosdep sources, a cache.

    Nothing of the machine's takes part -- not its bloom, not /etc/ros/rosdep, not ~/.ros. A
    source list there may redefine ROS keys for some platforms only, and every distro on another
    platform then fails to resolve them; bloom also runs `rosdep update` itself, rewriting
    whatever cache it is given. The rehearsal and the real release run in the same environment.
    """
    venv = root / "venv"
    run(sys.executable, "-m", "venv", str(venv))
    run(str(venv / "bin" / "pip"), "install", "-q", "bloom", "rosdep", "rosdistro")
    sources = root / "rosdep" / "sources.list.d"
    sources.mkdir(parents=True)
    (sources / "20-default.list").write_text(fetch_text(ROSDEP_SOURCES_URL), encoding="utf-8")
    for distro in ROS_DISTROS:
        subprocess.run([str(venv / "bin" / "rosdep"), "update", "--rosdistro", distro],  # nosec B603
                       env={**os.environ, **bloom_environment(root)}, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def bloom_environment(root):
    """The variables that point rosdep at ``root``'s sources and cache (the cache follows ROS_HOME)."""
    return {"ROSDEP_SOURCE_PATH": str(root / "rosdep" / "sources.list.d"), "ROS_HOME": str(root / "ros_home")}


def in_bloom_environment(root, command):
    """``command`` as one pasteable line inside that environment, refusing if it is not there."""
    exports = " ".join(f"{name}={value}" for name, value in bloom_environment(root).items())
    return f"test -d {root}/rosdep/sources.list.d && . {root}/venv/bin/activate && export {exports} && \\\n    {command}"


def release_tags(version):
    """The version tag and, beside it, the one each distro's bloom track exports from."""
    return [version, *(f"{distro}-{version}" for distro in ROS_DISTROS)]


def bloom_rehearsal_lines(root):
    return "\n\n".join(
        in_bloom_environment(root, f"bloom-release --pretend --no-web --rosdistro {distro} --track {distro} "
                                   f"--override-release-repository-url {root}/release-repository {ROSDISTRO_KEY}")
        for distro in ROS_DISTROS)


def bloom_release_lines(root):
    return "\n\n".join(
        in_bloom_environment(root, f"bloom-release --rosdistro {distro} --track {distro} {ROSDISTRO_KEY}")
        for distro in ROS_DISTROS)


# -- the GitHub Release -------------------------------------------------------------------

SECTION = re.compile(r"^(\d+\.\d+\.\d+ \(|Forthcoming$)")


def changelog_entries(path, version):
    """The entries of one CHANGELOG.rst section, wrapped lines joined, the contributor line dropped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(f"{version} (")]
    if not starts:
        return []
    entries = []
    for line in lines[starts[0] + 2:]:
        if SECTION.match(line):
            break
        if line.startswith("* "):
            entries.append(line[2:].strip())
        elif line.startswith("  ") and entries:
            entries[-1] += " " + line.strip()
    return [entry for entry in entries if not entry.startswith("Contributors:")]


def rst_to_markdown(text):
    """The inline reST a generated changelog carries: pull request links, links, literals."""
    text = re.sub(r"`#(\d+) <[^>]*>`_", r"#\1", text)
    text = re.sub(r"`([^`<]+?) <([^>]+)>`_", r"[\1](\2)", text)
    return text.replace("``", "`")


def release_notes(clone, version):
    """Every released package's entries for ``version``, each once, and how to install it."""
    paths = sorted(run("git", "ls-files", "*package.xml", cwd=clone).split(), key=lambda p: (p != PACKAGE_XML, p))
    entries = []
    for path in paths:
        if package_xml_field(clone / path, "version") != version:
            continue
        for entry in changelog_entries((clone / path).parent / "CHANGELOG.rst", version):
            if entry not in entries:
                entries.append(entry)
    if not entries:
        return None
    owner, name = REPO.split("/")
    ros_packages = ", ".join(f"`ros-{distro}-{DISTRIBUTION}*`" for distro in ROS_DISTROS)
    changes = "\n".join(f"- {rst_to_markdown(entry)}" for entry in entries)
    return f"""## Changes

{changes}

## Install

```bash
pip install {DISTRIBUTION}=={version}        # the core, ROS-free
```

The ROS packages ({ros_packages}) follow through the ROS build farm. Per-package changelogs are in
each package's `CHANGELOG.rst`; documentation at https://{owner}.github.io/{name}/.
"""


def github_release(clone, version):
    """The GitHub Release of the ``version`` tag, its notes from the changelogs; left alone if it exists."""
    exists = subprocess.run(["gh", "release", "view", version, "-R", REPO],  # nosec B603 B607
                            capture_output=True, check=False).returncode == 0
    if exists:
        ok(f"GitHub Release {version} exists; left as it is")
        return True
    notes = release_notes(clone, version)
    if notes is None:
        return not fail(f"no released package has a {version} changelog entry; nothing to announce")
    notes_file = CLONES / f"release-notes-{version}.md"
    notes_file.write_text(notes, encoding="utf-8")
    result = subprocess.run(["gh", "release", "create", version, "-R", REPO, "--verify-tag",  # nosec B603 B607
                             "--title", f"{DISTRIBUTION} {version}", "--notes-file", str(notes_file)],
                            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return not fail(f"GitHub Release {version} not created: {result.stderr.strip()} "
                        f"(retry: make release-github VERSION={version})")
    ok(f"GitHub Release {version}: {result.stdout.strip()}")
    return True


# -- the two commands ---------------------------------------------------------------------

def command_rc(version, commit):
    gated = gate(version, commit)
    if gated is None:
        return 1
    sha, clone = gated
    # The publish workflow's dispatch runs on the default branch's head, so the candidate is
    # always main's tip; a commit behind it cannot be tried this way.
    tip = run("git", "rev-parse", "origin/main", cwd=ROOT)
    if sha != tip:
        return fail(f"a candidate runs on origin/main's tip ({tip[:8]}), not {sha[:8]}")
    rc = f"{version}rc{next_rc(version)}"
    run("gh", "workflow", "run", "publish.yml", "-R", REPO, "-f", f"version={rc}")
    ok(f"dispatched publish.yml for {rc} -> TestPyPI")
    root = lay_out_bloom_rehearsal(clone, version)
    print(f"""
Watch it:   gh run watch -R {REPO} $(gh run list -R {REPO} -w publish.yml -L1 --json databaseId -q '.[0].databaseId')

Then test by hand, from a machine with nothing of ours on it:

    python3 -m venv /tmp/se && . /tmp/se/bin/activate
    pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ \\
        {DISTRIBUTION}=={rc}
    scenario_execution --help          # and a scenario of yours

And rehearse the build farm, once per distro -- the whole bloom release, pushing nothing (it
asks what the real one will ask; answer as you would then):

{bloom_rehearsal_lines(root)}

When both hold:  make release-final VERSION={version} COMMIT={sha[:12]}
""")
    return 0


def command_final(version, commit):
    gated = gate(version, commit)
    if gated is None:
        return 1
    sha, clone = gated
    if not rc_exists(version):
        return 1
    if run("git", "ls-remote", "--tags", "origin", version, cwd=clone):
        return fail(f"{version} already exists on {REPO}; a release is never re-tagged, the next one is the next number")
    # Lightweight, all of them: `git describe` prefers an annotated tag, and an annotated
    # <distro>-X.Y.Z would become "the latest tag", which the changelog generator refuses.
    tags = release_tags(version)
    for tag in tags:
        run("git", "tag", "-f", tag, cwd=clone)
    run("git", "push", "-q", "origin", *tags, cwd=clone)
    ok(f"pushed {', '.join(tags)} on {sha[:8]}; publish.yml -> PyPI runs now")
    announced = github_release(clone, version)
    root = CLONES / f"bloom-{version}"
    if root.exists():
        subprocess.run(["rm", "-rf", str(root)], check=True)  # nosec B603 B607
    root.mkdir(parents=True)
    lay_out_bloom_environment(root)
    ok(f"bloom environment laid out at {root.relative_to(ROOT)}")
    url = f"https://github.com/{REPO}.git"
    print(f"""
Watch it:   gh run list -R {REPO} -L3

Then the build farm, by hand, once per distro, before any further version bump lands on main
(bloom reads the version there) -- in the environment the rehearsal ran in, with access to the
release repository:

{bloom_release_lines(root)}

What bloom asks:
  - "Your track's 'actions' configuration is not the same as the default" -> n
  - "push to release repository?" -> y
  - a distro new to rosdistro: documentation and source -> git {url} @ main; status developed
Each run then opens a rosdistro pull request. Where bloom cannot (a token it is refused with),
open it by hand from a fork: each distro's `version:` line, and for a new distro its whole entry.
""")
    return 0 if announced else 1


def command_github_release(version):
    """The GitHub Release of an existing tag -- the step ``final`` ends with, on its own."""
    run("git", "fetch", "-q", "origin", "--tags", cwd=ROOT)
    found = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{version}^{{commit}}"],  # nosec B603 B607
                           cwd=ROOT, capture_output=True, text=True, check=False)
    if found.returncode != 0:
        return fail(f"no tag {version} on {REPO}; `final` creates it")
    return 0 if github_release(clean_clone(found.stdout.strip()), version) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("command", choices=("rc", "final", "github-release"))
    parser.add_argument("version", help="X.Y.Z -- the release, never a candidate number")
    parser.add_argument("--commit", help="a sha on main (default: origin/main's tip)")
    args = parser.parse_args()
    if not VERSION.match(args.version):
        return fail(f"{args.version!r} is not X.Y.Z; the candidate number is chosen here")
    if args.command == "rc":
        return command_rc(args.version, args.commit)
    if args.command == "github-release":
        return command_github_release(args.version)
    return command_final(args.version, args.commit)


if __name__ == "__main__":
    sys.exit(main())
