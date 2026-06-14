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

# --- ROS release (all packages; managed together via catkin tooling + bloom) ---
ROS_DISTRO ?= jazzy

# Fill the "Forthcoming" section of every CHANGELOG.rst from the git history.
# Review/edit the result, then run ros_release_prepare.
ros_changelog:
	catkin_generate_changelog --all

# Bump the version in every package.xml, rename "Forthcoming" to the new version,
# then commit and tag. Interactive: prompts for the new version. Push the tag afterwards.
ros_release_prepare:
	catkin_prepare_release

# Publish one package to the ROS build farm via bloom. Interactive and requires a
# configured release repository; run once per package, e.g.:
#   make ros_release ROS_PACKAGE=scenario_execution_ros ROS_DISTRO=jazzy
ros_release:
	@test -n "$(ROS_PACKAGE)" || { echo "Set ROS_PACKAGE=<package> (e.g. scenario_execution_ros)"; exit 1; }
	bloom-release --rosdistro $(ROS_DISTRO) --track $(ROS_DISTRO) $(ROS_PACKAGE)