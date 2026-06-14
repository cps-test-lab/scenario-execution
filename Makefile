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

test_scenario_execution_nav2_test:
	scenario_batch_execution -i test/scenario_execution_nav2_test/scenarios/ -o test_scenario_execution_nav2 --ignore-process-return-value -- ros2 run scenario_execution_ros scenario_execution_ros {SCENARIO} -o {OUTPUT_DIR} -t

test_scenario_execution_gazebo_test:
	scenario_batch_execution -i test/scenario_execution_gazebo_test/scenarios/ -o test_scenario_execution_gazebo --ignore-process-return-value -- ros2 launch tb4_sim_scenario sim_nav_scenario_launch.py scenario:={SCENARIO} output_dir:={OUTPUT_DIR} headless:=True use_rviz:=False navigation:=false

# --- PyPI release (core 'scenario_execution' package only; ROS/colcon packages are not published) ---
RELEASE_PKG_DIR = scenario_execution

release_tools:
	python3 -m pip install --upgrade build twine

release_version_check:
	@se_ver=$$(grep -oP "version='\K[^']+" $(RELEASE_PKG_DIR)/setup.py); \
	xml_ver=$$(grep -oP '<version>\K[^<]+' $(RELEASE_PKG_DIR)/package.xml); \
	if [ "$$se_ver" != "$$xml_ver" ]; then \
		echo "Version mismatch: setup.py=$$se_ver, package.xml=$$xml_ver. Sync them before releasing."; \
		exit 1; \
	fi; \
	echo "Releasing scenario_execution version $$se_ver"

release_clean:
	rm -rf $(RELEASE_PKG_DIR)/dist $(RELEASE_PKG_DIR)/build $(RELEASE_PKG_DIR)/*.egg-info

release_build: release_version_check release_clean
	cd $(RELEASE_PKG_DIR) && python3 -m build

# Validate the built artifacts (does not upload)
release_check: release_build
	python3 -m twine check $(RELEASE_PKG_DIR)/dist/*

# Upload to TestPyPI for a dry run (recommended before 'make release')
release_test: release_check
	python3 -m twine upload --repository testpypi $(RELEASE_PKG_DIR)/dist/*

# Publish to PyPI
release: release_check
	python3 -m twine upload $(RELEASE_PKG_DIR)/dist/*

# --- ROS release (managed together via catkin tooling + bloom) ---
ROS_DISTRO ?= jazzy
ROS_REPO   ?= scenario_execution

# Packages released to the ROS build farm. This MUST mirror the release/packages list
# for this repository in rosdistro (https://github.com/ros/rosdistro/blob/master/$(ROS_DISTRO)/distribution.yaml).
# Every other package in the workspace is intentionally NOT released and must stay
# disabled: the examples, the *_test packages, the simulation helpers
# (arm_sim_scenario, gazebo_static_camera, gazebo_tf_publisher, tb4_sim_scenario,
# message_modification, scenario_status, tf_to_pose_publisher), and the
# scenario_execution_{docker,kubernetes,moveit2,pybullet,floorplan_dsl} libraries.
# Do not add them here or to the rosdistro list.
ROS_RELEASE_PACKAGES = \
	scenario_execution \
	scenario_execution_control \
	scenario_execution_coverage \
	scenario_execution_dataops \
	scenario_execution_gazebo \
	scenario_execution_interfaces \
	scenario_execution_nav2 \
	scenario_execution_network \
	scenario_execution_os \
	scenario_execution_ros \
	scenario_execution_rviz \
	scenario_execution_sim \
	scenario_execution_x11

# Fill the "Forthcoming" section of every CHANGELOG.rst from the git history.
# (No --all: every package already has a CHANGELOG.rst.) Review/edit the result,
# then bump the version (make set_version) and tag.
ros_changelog:
	catkin_generate_changelog

# Set the version across every source package.xml and setup.py (ROS + PyPI).
# Usage: make set_version VERSION=1.6.0      (explicit)
#        make set_version VERSION=minor      (bump major|minor|patch from current)
# Afterwards review the diff, update the CHANGELOG.rst headings, then commit and tag:
#        git commit -am "<version>" && git tag <version>
set_version:
	@test -n "$(VERSION)" || { echo "Usage: make set_version VERSION=<X.Y.Z|major|minor|patch>"; exit 1; }
	python3 tools/set_version.py "$(VERSION)"

# Print the packages that are released vs. intentionally disabled, so the rosdistro
# pull request can be reviewed before publishing.
ros_release_packages:
	@echo "Released to ROS ($(ROS_DISTRO)):"; for p in $(ROS_RELEASE_PACKAGES); do echo "  + $$p"; done
	@echo "Disabled (kept out of the release):"; \
	for f in $$(find . -name package.xml -not -path '*/install/*' -not -path '*/build/*'); do \
		basename $$(dirname $$f); \
	done | sort -u | grep -vxF "$$(printf '%s\n' $(ROS_RELEASE_PACKAGES))" | sed 's/^/  - /'

# Publish the repository to the ROS build farm via bloom. Interactive; requires a
# configured release repository and opens a rosdistro pull request. bloom takes the
# rosdistro *repository* key ($(ROS_REPO)), not individual package names. The set of
# released packages is governed by rosdistro's release/packages list (mirrored in
# ROS_RELEASE_PACKAGES) — keep the disabled packages out of it.
# Usage: make ros_release [ROS_DISTRO=jazzy]
ros_release:
	bloom-release --rosdistro $(ROS_DISTRO) --track $(ROS_DISTRO) $(ROS_REPO)