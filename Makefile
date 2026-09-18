file_finder = find . -type f $(1) -not \( -path './venv/*' -o -path './build/*' -o -path './log/*' -o -path './install/*' -o -path './dependencies/*' \)

PY_FILES = $(call file_finder,-name "*.py")
CPP_FILES = $(call file_finder,-name "*.cpp")
H_FILES = $(call file_finder,-name "*.h")

LINKCHECKDIR  = build/linkcheck

check: check_format pylint

format:
	$(PY_FILES) | xargs autopep8 --in-place --max-line-length=140
	$(CPP_FILES) | xargs clang-format -i
	$(H_FILES) | xargs clang-format -i

check_format:
	$(PY_FILES) | xargs autopep8 --diff --max-line-length=140 --exit-code

pylint:
	$(PY_FILES) | xargs pylint --rcfile=.github/linters/.pylintrc

sphinx_setup:
	if [ ! -d "venv" ]; then \
		python -m venv venv/; \
		. venv/bin/activate; \
		pip install -r docs/requirements.txt; \
		deactivate; \
	fi

doc: sphinx_setup checklinks checkspelling
	. venv/bin/activate && GITHUB_REF_NAME=local GITHUB_REPOSITORY=intellabs/scenario_execution python -m sphinx -b html -W docs build/html

view_doc: doc
	firefox build/html/index.html &

checklinks: sphinx_setup
	. venv/bin/activate && GITHUB_REF_NAME=local GITHUB_REPOSITORY=intellabs/scenario_execution python -m sphinx -b html -b linkcheck -W docs $(ALLSPHINXOPTS) $(LINKCHECKDIR)
	@echo
	@echo "Check finished. Report is in $(LINKCHECKDIR)."

checkspelling: sphinx_setup
	. venv/bin/activate && GITHUB_REF_NAME=local GITHUB_REPOSITORY=intellabs/scenario_execution python -m sphinx -b html -b spelling -W docs $(ALLSPHINXOPTS) $(LINKCHECKDIR)
	@echo
	@echo "Check finished. Report is in $(LINKCHECKDIR)."

# --- Unit tests -------------------------------------------------------------------------
# colcon is what CI runs; the pytest targets are the same suites without the build, for a
# tree that is already built and sourced.
TEST_PACKAGES = scenario_execution scenario_execution_ros

test:
	colcon test --packages-select $(TEST_PACKAGES) --event-handlers console_direct+ --return-code-on-test-failure

test_core:
	python3 -m pytest scenario_execution/test

test_ros:
	python3 -m pytest scenario_execution_ros/test

test_scenario_execution_nav2_test:
	scenario_batch_execution -i test/scenario_execution_nav2_test/scenarios/ -o test_scenario_execution_nav2 --ignore-process-return-value -- ros2 run scenario_execution_ros scenario_execution_ros {SCENARIO} -o {OUTPUT_DIR} -t

test_scenario_execution_gazebo_test:
	scenario_batch_execution -i test/scenario_execution_gazebo_test/scenarios/ -o test_scenario_execution_gazebo --ignore-process-return-value -- ros2 launch tb4_sim_scenario sim_nav_scenario_launch.py scenario:={SCENARIO} output_dir:={OUTPUT_DIR} headless:=True use_rviz:=False navigation:=false

# --- PyPI release (core 'scenario_execution' package only; ROS/colcon packages are not published) ---
RELEASE_PKG_DIR = scenario_execution

# --- OSC2 parser generation ------------------------------------------------------------
# The generated ANTLR parser is committed, so this only needs running when the grammar
# changes. Pinned to 4.9.1: that is the version the committed files were generated with,
# and ANTLR 4.10+ changes the Python runtime API (serializedATN shape), which would
# require moving the antlr4-python3-runtime pin in lockstep.
#
# Regenerating without the post-processing step silently drops the license headers and
# reintroduces a `typing.io` import that does not exist on Python 3.13 -- see
# tools/antlr_postprocess.py. Always go through this target rather than calling antlr
# by hand.
ANTLR_VERSION = 4.9.1
ANTLR_JAR = dependencies/antlr-$(ANTLR_VERSION)-complete.jar
# The jar is fetched over the network and then executed, so pin what we expect to run.
# This digest is the artifact that reproduces the committed generated files byte for byte.
ANTLR_JAR_SHA256 = 1f645aea79b98e6ff7ec8f6bf7ea82b58cfc60a194cda2a3b1e753589d41f98d
GRAMMAR_DIR = scenario_execution/scenario_execution/osc2_parsing
GENERATED_PY = $(GRAMMAR_DIR)/OpenSCENARIO2Lexer.py \
               $(GRAMMAR_DIR)/OpenSCENARIO2Parser.py \
               $(GRAMMAR_DIR)/OpenSCENARIO2Listener.py \
               $(GRAMMAR_DIR)/OpenSCENARIO2Visitor.py

$(ANTLR_JAR):
	mkdir -p $(dir $@)
	curl -fsSL -o $@.tmp https://www.antlr.org/download/antlr-$(ANTLR_VERSION)-complete.jar
	@echo "$(ANTLR_JAR_SHA256)  $@.tmp" | sha256sum --check --status \
		|| { echo "ANTLR jar digest mismatch -- refusing to run it"; rm -f $@.tmp; exit 1; }
	mv $@.tmp $@

# antlr mirrors the input path underneath -o, so generating from the repo root would
# bury the output in a nested tree and silently leave the committed files untouched.
# Run it from the grammar directory instead, as the generated files must land beside it.
parser: $(ANTLR_JAR)
	cd $(GRAMMAR_DIR) && java -jar $(abspath $(ANTLR_JAR)) \
		-Dlanguage=Python3 -visitor -listener OpenSCENARIO2.g4
	python3 tools/antlr_postprocess.py $(GENERATED_PY)
	@echo "Regenerated. Review 'git diff -- $(GRAMMAR_DIR)': a grammar change confined to"
	@echo "the lexer should leave Parser/Listener/Visitor and the .tokens files untouched."


# --- The release, from here to the tag ---------------------------------------------------
#
# A release is prepared here and published by CI: `make release-prepare VERSION=X.Y.Z` writes
# the changelogs and the version, that goes up as a pull request, and the tag pushed after the
# merge is what .github/workflows/publish.yml builds and uploads (to TestPyPI first, from a
# workflow dispatch; to PyPI from the tag). Nothing is uploaded from a developer machine.
#
# The version lives in package.xml alone and every setup.py reads it from there, so the only
# files a release changes are the released packages' package.xml and CHANGELOG.rst; every
# package that is never released is fixed at 0.0.0 (`make release-list` shows both sets).
# docs/development.rst, "Releasing", is the whole sequence.

release-prepare:
	@test -n "$(VERSION)" || { echo "Usage: make release-prepare VERSION=<X.Y.Z|major|minor|patch>"; exit 1; }
	@python3 -c "import catkin_pkg" 2>/dev/null || { echo "catkin_pkg is not installed. Install with: python3 -m pip install catkin_pkg"; exit 1; }
	python3 tools/release_prepare.py "$(VERSION)"

release-list:
	@python3 tools/release_prepare.py --list

# Once the release pull request is merged: the candidate, then -- after it was tried by hand --
# the tag. Both refuse on a commit that is not on main, on red CI, on a tree whose version is
# not VERSION, and on a package that is neither released nor ignored by bloom; the final also
# refuses without a candidate on TestPyPI. Each prints what to do next.
release-rc:
	@test -n "$(VERSION)" || { echo "Usage: make release-rc VERSION=X.Y.Z [COMMIT=<sha on main>]"; exit 1; }
	python3 tools/release.py rc "$(VERSION)" $(if $(COMMIT),--commit "$(COMMIT)",)

release-final:
	@test -n "$(VERSION)" || { echo "Usage: make release-final VERSION=X.Y.Z [COMMIT=<sha on main>]"; exit 1; }
	python3 tools/release.py final "$(VERSION)" $(if $(COMMIT),--commit "$(COMMIT)",)

# What the publish workflow builds and checks, runnable here: the sdist and the wheel of the
# one PyPI distribution, validated by twine, at the version package.xml says.
release_check:
	rm -rf $(RELEASE_PKG_DIR)/dist $(RELEASE_PKG_DIR)/build $(RELEASE_PKG_DIR)/*.egg-info
	cd $(RELEASE_PKG_DIR) && python3 -m build
	python3 -m twine check $(RELEASE_PKG_DIR)/dist/*

# --- The ROS build farm, after the tag -----------------------------------------------------
ROS_DISTRO ?= jazzy
ROS_REPO   ?= scenario_execution

# Which packages bloom releases is decided by their version: a package at the release
# version is released, one at 0.0.0 is not (`make release-list`). bloom itself drops the
# packages named in the release repository's <distro>.ignored before it checks that the rest
# share one version, so that file and the 0.0.0 set have to agree, and rosdistro's
# release/packages list is what bloom produces from the rest. A package that is in neither
# fails bloom loudly rather than being released by accident.
#
# Interactive; needs a current bloom, the release repository, and both tags (X.Y.Z and
# <distro>-X.Y.Z, the one bloom exports from) on the upstream. It reads the version from the
# tip of main, so run it before the next bump lands there. Opens the rosdistro pull request.
# Usage: make ros_release [ROS_DISTRO=jazzy]
ros_release:
	bloom-release --rosdistro $(ROS_DISTRO) --track $(ROS_DISTRO) $(ROS_REPO)
