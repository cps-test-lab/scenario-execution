# Copyright (C) 2024 Intel Corporation
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

import importlib
import inspect
import os
import sys
import time
import argparse
import signal
from datetime import datetime, timedelta
import py_trees
from scenario_execution.model.osc2_parser import OpenScenario2Parser
from scenario_execution.utils.logging import Logger
from scenario_execution.model.model_file_loader import ModelFileLoader
from scenario_execution.simulation import SimulationClock
from dataclasses import dataclass
from xml.sax.saxutils import escape  # nosec B406 # escape is only used on an internally generated error string
from timeit import default_timer as timer
import subprocess  # nosec B404


def _get_missing_reset_params(simulation, scenario_params: dict) -> set:
    """Return the set of parameter names that ``simulation.reset()`` requires
    but are absent from *scenario_params*.

    Only the concrete override of ``reset()`` is inspected — ``self`` is
    excluded.  Parameters that carry a default value are considered optional
    and are not flagged.
    """
    sig = inspect.signature(type(simulation).reset)
    missing = set()
    for name, param in sig.parameters.items():
        if name == 'self':
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if param.default is inspect.Parameter.empty:
            if name not in (scenario_params or {}):
                missing.add(name)
    return missing


def _build_reset_kwargs(simulation, scenario_params: dict) -> dict:
    """Build the keyword-argument dict for calling ``simulation.reset()``.

    Each named parameter in the concrete ``reset()`` override is looked up in
    *scenario_params* and forwarded so the implementation can use plain
    Python parameter names instead of unpacking a dict manually.
    """
    sig = inspect.signature(type(simulation).reset)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name == 'self':
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        value = (scenario_params or {}).get(name, param.default)
        if value is not inspect.Parameter.empty:
            kwargs[name] = value
    return kwargs


class ScenarioExecutionConfig:
    _instance = None
    scenario_file_directory = None
    output_directory = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance


class ShutdownHandler:
    _instance = None

    def __init__(self):
        self.futures = []

    def get_instance():  # pylint: disable=no-method-argument
        if ShutdownHandler._instance is None:
            ShutdownHandler._instance = ShutdownHandler()
        return ShutdownHandler._instance

    def add_future(self, future):
        self.futures.append(future)

    def is_done(self):
        return all(fut.done() for fut in self.futures)


@dataclass
class ScenarioResult:
    name: str
    result: bool
    failure_message: str
    failure_output: str = ""
    processing_time: timedelta = timedelta(0)
    start_time: datetime = None
    output_dir: str = None


class LastSnapshotVisitor(py_trees.visitors.DisplaySnapshotVisitor):

    def __init__(self):
        self.last_snapshot = ""
        super().__init__()

    def finalise(self) -> None:
        if self.root is not None:
            self.last_snapshot = py_trees.display.unicode_tree(
                root=self.root,
                show_only_visited=self.display_only_visited_behaviours,
                show_status=False,
                visited=self.visited,
                previously_visited=self.previously_visited
            )


class ScenarioExecution(object):
    """
    Base class for scenario execution.
    Override method run() and method setup_behaviour_tree() to adapt to other middlewares.
    This class can also be executed standalone
    """

    def __init__(self,
                 debug: bool,
                 log_model: bool,
                 live_tree: bool,
                 scenario_file: str,
                 output_dir: str,
                 dry_run=False,
                 render_dot=False,
                 setup_timeout=py_trees.common.Duration.INFINITE,
                 tick_period: float = 0.1,
                 scenario_parameter_file=None,
                 create_scenario_parameter_file_template=None,
                 post_run=None,
                 logger=None,
                 register_signal=True,
                 simulation=None,
                 output_result_per_scenario: bool = False) -> None:

        def signal_handler(sig, frame):
            self.on_scenario_shutdown(False, "Aborted")

        if register_signal:
            signal.signal(signal.SIGHUP, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

        self.current_scenario_start = None
        self.current_scenario = None
        self.debug = debug
        self.log_model = log_model
        self.live_tree = live_tree
        self.scenario_file = scenario_file
        ScenarioExecutionConfig().scenario_file_directory = os.path.abspath(os.path.dirname(scenario_file)) if scenario_file else None
        self.output_dir = output_dir
        ScenarioExecutionConfig().output_directory = os.path.abspath(output_dir) if output_dir else None
        self.dry_run = dry_run
        self.render_dot = render_dot
        self.post_run = []
        for cmd in (post_run or []):
            if not os.path.isfile(cmd):
                raise ValueError(f"Post-run command '{cmd}' does not exist.")
            if not os.access(cmd, os.X_OK):
                raise ValueError(f"Post-run command '{cmd}' is not executable.")
            self.post_run.append(os.path.abspath(cmd))
        if self.output_dir and not self.dry_run:
            self.output_dir = os.path.abspath(self.output_dir)
            if not os.path.isdir(self.output_dir):
                try:
                    os.mkdir(self.output_dir)
                except OSError as e:
                    raise ValueError(f"Could not create output directory: {e}") from e
            if not os.access(self.output_dir, os.W_OK):
                raise ValueError(f"Output directory '{self.output_dir}' not writable.")
            if os.path.exists(os.path.join(self.output_dir, 'test.xml')):
                os.remove(os.path.join(self.output_dir, 'test.xml'))
        if not logger:
            self.logger = Logger('scenario_execution', debug)
        else:
            self.logger = logger

        if self.post_run and not self.output_dir:
            self.logger.warning("--post-run is set but no --output-dir specified. Post-run commands will receive an empty output directory.")

        if self.debug:
            py_trees.logging.level = py_trees.logging.Level.DEBUG
        self.setup_timeout = setup_timeout
        self.tick_period = tick_period
        self.scenarios = None
        self.blackboard = None
        self.behaviour_tree = None
        self.last_snapshot_visitor = None
        self.shutdown_requested = False
        self.results = []
        self.create_scenario_parameter_file_template = create_scenario_parameter_file_template
        self.scenario_parameter_file = scenario_parameter_file
        self.simulation = simulation
        self.scenario_params = {}
        self.scenarios_list = []
        self.output_result_per_scenario = output_result_per_scenario
        self.current_scenario_output_dir = None

    def setup(self, scenario: py_trees.behaviour.Behaviour, current_output_dir=None, **kwargs) -> bool:
        """
        Setup each scenario before ticking

        Args:
            tree [py_trees.behavior.Behavior]: root of the tree
            current_output_dir: per-scenario output directory override; if None, uses self.output_dir

        return:
            True if the scenario is setup without errors
        """
        effective_output_dir = current_output_dir if current_output_dir is not None else self.output_dir
        ScenarioExecutionConfig().output_directory = os.path.abspath(effective_output_dir) if effective_output_dir else None
        self.current_scenario_output_dir = effective_output_dir
        self.logger.info(f"Executing scenario '{scenario.name}'")
        self.shutdown_requested = False
        self.current_scenario = scenario
        self.current_scenario_start = datetime.now()
        self.blackboard = scenario.attach_blackboard_client(name="MainBlackboardClient", namespace=scenario.name)

        # Initialize end and fail events
        self.blackboard.register_key("end", access=py_trees.common.Access.WRITE)
        self.blackboard.register_key("fail", access=py_trees.common.Access.WRITE)
        self.blackboard.end = False
        self.blackboard.fail = False
        self.behaviour_tree = self.setup_behaviour_tree(scenario)  # Get the behaviour_tree
        self.behaviour_tree.add_pre_tick_handler(self.pre_tick_handler)
        self.behaviour_tree.add_post_tick_handler(self.post_tick_handler)
        self.last_snapshot_visitor = LastSnapshotVisitor()
        self.behaviour_tree.add_visitor(self.last_snapshot_visitor)
        if self.debug:
            self.behaviour_tree.add_visitor(py_trees.visitors.DebugVisitor())
        if self.live_tree:
            self.behaviour_tree.add_visitor(
                py_trees.visitors.DisplaySnapshotVisitor(
                    display_blackboard=True
                ))
        input_dir = None
        if self.scenario_file:
            input_dir = os.path.dirname(self.scenario_file)
        self.behaviour_tree.setup(timeout=self.setup_timeout,
                                  logger=self.logger,
                                  input_dir=input_dir,
                                  output_dir=effective_output_dir,
                                  tick_period=self.tick_period,
                                  **kwargs)
        self.post_setup()

    def setup_behaviour_tree(self, tree):
        """
        Setup the behaviour tree.

        For other middleware, a subclass of behaviour_tree might be needed for additional support.
        Override this to adapt to other middleware.

        Args:
            tree [py_trees.behaviour.Behaviour]: root of the behaviour tree

        return:
            py_trees.trees.BehaviourTree
        """
        return py_trees.trees.BehaviourTree(tree)

    def post_setup(self):
        pass

    def parse(self):  # pylint: disable=too-many-return-statements
        """
        Parse the OpenScenario2 file

        return:
            True if no errors occured during parsing
        """
        if self.scenario_file is None:
            self.logger.error(f"No scenario file given.")
            return False
        start = datetime.now()
        file_extension = os.path.splitext(self.scenario_file)[1]
        if file_extension not in ('.osc', '.sce'):
            self.add_result(ScenarioResult(name=f'Parsing of {self.scenario_file}',
                                           result=False,
                                           failure_message="parsing failed",
                                           failure_output=f"File has unknown extension '{file_extension}'. Allowed [.osc, .sce]",
                                           processing_time=datetime.now() - start,
                                           start_time=start))
            return False

        if not os.path.isfile(self.scenario_file):
            self.add_result(ScenarioResult(name=f'Parsing of {self.scenario_file}',
                                           result=False,
                                           failure_message="parsing failed",
                                           failure_output="File does not exist",
                                           processing_time=datetime.now() - start,
                                           start_time=start))
            return False

        if file_extension == '.osc':
            parser = OpenScenario2Parser(self.logger)
        else:
            parser = ModelFileLoader(self.logger)
        try:
            self.scenarios_list = parser.process_file(self.scenario_file, self.log_model, self.debug, self.scenario_parameter_file, self.create_scenario_parameter_file_template)
            if self.create_scenario_parameter_file_template:
                return True
        except Exception as e:  # pylint: disable=broad-except
            self.add_result(ScenarioResult(name=f'Parsing of {self.scenario_file}',
                                           result=False,
                                           failure_message="parsing failed",
                                           failure_output=str(e),
                                           processing_time=datetime.now() - start,
                                           start_time=start))
            return False

        if self.scenarios_list:
            self.tree, self.scenario_params, _ = self.scenarios_list[0]
        if self.render_dot:
            for tree, _, __ in self.scenarios_list:
                self.logger.info(f"Writing py-trees dot files to {tree.name.lower()}.[dot|svg|png] ...")
                py_trees.display.render_dot_tree(tree, target_directory=self.output_dir)
        return True

    def run(self):
        if self.simulation is not None:
            self.run_with_simulation(self.simulation)
            return

        multiple_scenarios = len(self.scenarios_list) > 1
        for tree, _, scenario_output_dir_override in self.scenarios_list:
            effective_output_dir = self._resolve_scenario_output_dir(
                tree.name, scenario_output_dir_override, multiple_scenarios)
            if effective_output_dir is None and multiple_scenarios and self.output_dir:
                return  # error already reported via on_scenario_shutdown
            try:
                self.setup(tree, current_output_dir=effective_output_dir)
            except Exception as e:  # pylint: disable=broad-except
                self.on_scenario_shutdown(False, "Setup failed", f"{e}")
                return

            while not self.shutdown_requested:
                try:
                    start = timer()
                    self.behaviour_tree.tick()
                    end = timer()
                    tick_time = end - start
                    sleep_time = self.tick_period - tick_time
                    if sleep_time < 0:
                        self.logger.warning(f"Tick too long: {tick_time} > {self.tick_period}")
                    else:
                        time.sleep(self.tick_period - tick_time)
                    if self.live_tree:
                        self.logger.debug(py_trees.display.unicode_tree(
                            root=self.behaviour_tree.root, show_status=True))
                except KeyboardInterrupt:
                    self.on_scenario_shutdown(False, "Aborted")
                    return

    def run_with_simulation(self, simulation):
        """Run scenario execution driven by a step-based SimulationInterface.

        The simulation controls time: each call to ``simulation.step()`` advances
        the world by ``simulation.dt`` seconds and ``SimulationClock`` by the same
        amount. No ``time.sleep()`` is used — the loop runs as fast as the
        simulation allows.

        Lifecycle across all scenarios in the file:
            1. ``simulation.setup()`` — called once
            2. For each scenario: ``simulation.reset()`` → tick loop
            3. ``simulation.shutdown()`` — called once in a ``finally`` block
        """
        clock = SimulationClock(simulation.dt)
        self.tick_period = simulation.dt

        try:
            simulation.setup(
                logger=self.logger,
                output_dir=self.output_dir,
                tick_period=self.tick_period,
            )
        except Exception as e:  # pylint: disable=broad-except
            self.on_scenario_shutdown(False, "Simulation setup failed", f"{e}")
            return

        multiple_scenarios = len(self.scenarios_list) > 1
        try:
            for tree, params, scenario_output_dir_override in self.scenarios_list:
                effective_output_dir = self._resolve_scenario_output_dir(
                    tree.name, scenario_output_dir_override, multiple_scenarios)
                if effective_output_dir is None and multiple_scenarios and self.output_dir:
                    return  # error already reported via on_scenario_shutdown

                missing = _get_missing_reset_params(simulation, params)
                if missing:
                    self.on_scenario_shutdown(
                        False,
                        "Simulation reset parameter mismatch",
                        f"reset() requires parameter(s) {sorted(missing)} but they are not "
                        f"defined in the OSC scenario file.",
                    )
                    return

                try:
                    reset_kwargs = _build_reset_kwargs(simulation, params)
                    simulation.reset(**reset_kwargs)
                except Exception as e:  # pylint: disable=broad-except
                    self.on_scenario_shutdown(False, "Simulation reset failed", f"{e}")
                    return

                clock.reset()

                try:
                    self.setup(tree, current_output_dir=effective_output_dir, simulation=simulation, clock=clock)
                except Exception as e:  # pylint: disable=broad-except
                    self.on_scenario_shutdown(False, "Setup failed", f"{e}")
                    return

                try:
                    while not self.shutdown_requested:
                        simulation.step()
                        clock.advance()
                        self.behaviour_tree.tick()
                        if self.live_tree:
                            self.logger.debug(py_trees.display.unicode_tree(
                                root=self.behaviour_tree.root, show_status=True))
                except KeyboardInterrupt:
                    self.on_scenario_shutdown(False, "Aborted")
                    return
        finally:
            try:
                simulation.shutdown()
            except Exception as e:  # pylint: disable=broad-except
                self.logger.error(f"Simulation shutdown error: {e}")

    def _resolve_scenario_output_dir(self, scenario_name: str, override: str | None, multiple_scenarios: bool):
        """Determine the effective output directory for a scenario.

        For a single scenario, returns ``self.output_dir`` unchanged.
        For multiple scenarios, creates (if necessary) and returns a subdirectory
        under ``self.output_dir`` named after *override* (if set) or *scenario_name*.

        If *override* is an absolute path it is used directly without joining against
        ``self.output_dir``.  The directory is created (``makedirs``) but no existing
        files inside it are removed.

        Returns ``None`` (and logs an error via :meth:`on_scenario_shutdown`) if the
        subdirectory cannot be created.
        """
        if not multiple_scenarios or not self.output_dir:
            return self.output_dir
        if override and os.path.isabs(override):
            effective = override
        else:
            subdir_name = override if override else scenario_name
            effective = os.path.join(self.output_dir, subdir_name)
        if not os.path.isdir(effective):
            try:
                os.makedirs(effective, exist_ok=True)
            except OSError as e:
                self.on_scenario_shutdown(False, "Could not create scenario output directory", f"{e}")
                return None
        return effective

    def add_result(self, result: ScenarioResult):
        if result.result is False:
            self.logger.error(f"{result.name}: {result.failure_message} {result.failure_output}")
        self.results.append(result)

    def _write_test_xml(self, output_dir: str, results: list):
        """Write a JUnit-compatible test.xml for *results* into *output_dir*."""
        result_file = os.path.join(output_dir, 'test.xml')
        failures = sum(1 for r in results if r.result is False)
        overall_time = sum((r.processing_time for r in results), timedelta(0))
        try:
            with open(result_file, 'w') as out:
                out.write('<?xml version="1.0" encoding="utf-8"?>\n')
                out.write(
                    f'<testsuite errors="0" failures="{failures}" name="scenario_execution"'
                    f' tests="{len(results)}" time="{overall_time.total_seconds()}">\n')
                for res in results:
                    out.write(
                        f'  <testcase classname="tests.scenario" name="{res.name}" time="{res.processing_time.total_seconds()}">\n')
                    if res.start_time:
                        out.write(f'    <properties>\n')
                        out.write(f'      <property name="start_time" value="{res.start_time.timestamp():.6f}"/>\n')
                        out.write(f'    </properties>\n')
                    if res.result is False:
                        failure_text = escape(res.failure_output).replace('"', "'")
                        out.write(f'    <failure message="{res.failure_message}">{failure_text}</failure>\n')
                    out.write(f'  </testcase>\n')
                out.write("</testsuite>\n")
        except Exception as e:  # pylint: disable=broad-except
            # use print, as logger might not be available during shutdown
            print(f"Could not write results to '{output_dir}': {e}")

    def process_results(self):
        result = True
        if len(self.results) == 0 and not self.dry_run:
            result = False

        for res in self.results:
            if res.result is False:
                result = False

        # store output file
        if self.output_dir:
            if self.dry_run:
                print("Dry_run is enabled, no output files will be generated!")
            elif self.results:
                multiple_scenarios = len(self.scenarios_list) > 1
                if multiple_scenarios and self.output_result_per_scenario:
                    # Write one test.xml per scenario output directory (grouped when
                    # multiple scenarios share the same _output_dir).
                    results_by_dir = {}
                    for res in self.results:
                        dir_key = res.output_dir or self.output_dir
                        results_by_dir.setdefault(dir_key, []).append(res)
                    for output_dir, dir_results in results_by_dir.items():
                        self._write_test_xml(output_dir, dir_results)
                else:
                    self._write_test_xml(self.output_dir, self.results)

                # Run post-run commands if specified (always against the root output_dir)
                for cmd in self.post_run:
                    self.logger.info(f"Running post-run: {cmd} {self.output_dir}")
                    try:
                        # start_new_session=True puts the child in its own process group
                        # so its grandchildren never get re-parented to scenario-execution
                        # and we can kill the whole group cleanly on timeout.
                        with subprocess.Popen([cmd, self.output_dir or ""],
                                              start_new_session=True) as proc:
                            try:
                                proc.wait(timeout=600)
                            except subprocess.TimeoutExpired:
                                try:
                                    os.killpg(proc.pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                                try:
                                    proc.wait(timeout=5)
                                except subprocess.TimeoutExpired:
                                    try:
                                        os.killpg(proc.pid, signal.SIGKILL)
                                    except ProcessLookupError:
                                        pass
                                    proc.wait()
                                self.logger.error(f"Post-run '{cmd}' timed out after 600s.")
                                continue
                            if proc.returncode != 0:
                                self.logger.error(
                                    f"Post-run '{cmd}' failed with exit code {proc.returncode}.")
                    except Exception as e:  # pylint: disable=broad-except
                        self.logger.error(f"Post-run '{cmd}' error: {e}")
        return result

    def pre_tick_handler(self, behaviour_tree):
        """
        Things to do before a round of ticking
        """
        if self.live_tree:
            self.logger.debug(
                f"--------- Scenario {behaviour_tree.root.name}: Run {behaviour_tree.count} ---------")

    def post_tick_handler(self, behaviour_tree):
        # Shut down if the root has failed
        if self.behaviour_tree.root.status == py_trees.common.Status.FAILURE:
            self.blackboard.fail = True
        if self.behaviour_tree.root.status == py_trees.common.Status.SUCCESS:
            self.blackboard.end = True
        if self.blackboard.fail or self.blackboard.end:
            result = True
            if self.blackboard.fail:
                result = False
            if not self.shutdown_requested:
                self.on_scenario_shutdown(result)

    def on_scenario_shutdown(self, result, failure_message="", failure_output=""):
        self.shutdown_requested = True
        if self.behaviour_tree:
            self.behaviour_tree.interrupt()
        if self.current_scenario:
            if result:
                self.logger.info(f"Scenario '{self.current_scenario.name}' succeeded.")
            else:
                if not failure_message:
                    failure_message = "execution failed."
                if failure_output and self.last_snapshot_visitor.last_snapshot:
                    failure_output += "\n\n"
                failure_output += self.last_snapshot_visitor.last_snapshot
                if self.log_model:
                    self.logger.error(self.last_snapshot_visitor.last_snapshot)
            self.add_result(ScenarioResult(name=self.current_scenario.name,
                                           result=result,
                                           failure_message=failure_message,
                                           failure_output=failure_output,
                                           processing_time=datetime.now()-self.current_scenario_start,
                                           start_time=self.current_scenario_start,
                                           output_dir=self.current_scenario_output_dir))
        else:
            self.add_result(ScenarioResult(name="",
                                           result=result,
                                           failure_message=failure_message,
                                           failure_output=failure_output,
                                           start_time=datetime.now(),
                                           output_dir=self.current_scenario_output_dir))

    @staticmethod
    def get_arg_parser():
        parser = argparse.ArgumentParser()
        parser.add_argument('-d', '--debug', action='store_true', help='debugging output')
        parser.add_argument('-l', '--log-model', action='store_true',
                            help='Produce tree output of parsed openscenario2 content')
        parser.add_argument('-t', '--live-tree', action='store_true',
                            help='For debugging: Show current state of py tree')
        parser.add_argument('-o', '--output-dir', type=str, help='Directory for output (e.g. test results)')
        parser.add_argument('-n', '--dry-run', action='store_true', help='Parse and resolve scenario, but do not execute')
        parser.add_argument('--dot', action='store_true', help='Render dot trees of resulting py-tree')
        parser.add_argument('-s', '--step-duration', type=float, help='Duration between the behavior tree step executions', default=0.1)
        parser.add_argument('--scenario-parameter-file', type=str,
                            help='File specifying scenario parameter. These will override default values.')
        parser.add_argument('--create-scenario-parameter-file-template',action='store_true', help='Command to run to create a scenario parameter file template specified by --scenario-parameter-file')
        parser.add_argument('--post-run', action='append', dest='post_run', metavar='POST_RUN_COMMAND',
                            help='Command to run after scenario execution (expected commandline: <command> <output_dir>). Can be specified multiple times; commands are executed in order.')
        parser.add_argument('--simulation', type=str, metavar='MODULE:CLASS',
                            help='Step-based simulation interface to use. '
                                 'Accepts a module path ("module.path:ClassName") or a file path '
                                 '("path/to/file.py" or "path/to/file.py:ClassName"). '
                                 'The class must implement SimulationInterface.')
        parser.add_argument('--output-result-per-scenario', action='store_true', dest='output_result_per_scenario',
                            help='When multiple scenarios are defined (either in the .osc file or via '
                                 'multiple --scenario-parameter-file documents), write a separate '
                                 'test.xml inside each scenario\'s output subdirectory instead of a '
                                 'single combined test.xml in the root output directory. '
                                 'Has no effect when only one scenario is executed.')
        parser.add_argument('scenario', type=str, help='scenario file to execute', nargs='?')
        return parser


def _load_simulation(spec: str, kwargs: dict | None = None):
    """Dynamically import and instantiate a SimulationInterface from a 'module:Class' spec
    or a file path spec ('path/to/file.py' or 'path/to/file.py:ClassName')."""
    import inspect

    # Determine if this looks like a file path (contains '/' or ends with '.py')
    # Split off an optional ':ClassName' suffix first
    if ':' in spec:
        path_or_module, class_name = spec.rsplit(':', 1)
    else:
        path_or_module, class_name = spec, None

    is_file_path = '/' in path_or_module or path_or_module.endswith('.py')

    if is_file_path:
        file_path = os.path.abspath(path_or_module)
        if not os.path.isfile(file_path):
            print(f"Error: Simulation file not found: '{file_path}'")
            sys.exit(1)
        module_name = os.path.splitext(os.path.basename(file_path))[0]
        loader_spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(loader_spec)
        try:
            loader_spec.loader.exec_module(module)
        except Exception as e:  # pylint: disable=broad-except
            print(f"Error: Could not load simulation file '{file_path}': {e}")
            sys.exit(1)
    else:
        if class_name is None:
            print(f"Error: --simulation must be in 'module.path:ClassName' format or a file path, got '{spec}'")
            sys.exit(1)
        try:
            module = importlib.import_module(path_or_module)
        except ImportError as e:
            print(f"Error: Could not import simulation module '{path_or_module}': {e}")
            sys.exit(1)

    if class_name:
        cls = getattr(module, class_name, None)
        if cls is None:
            print(f"Error: Class '{class_name}' not found in '{path_or_module}'")
            sys.exit(1)
    else:
        # Auto-detect: find the first class defined in the module that looks like a simulation
        candidates = [
            obj for name, obj in inspect.getmembers(module, inspect.isclass)
            if obj.__module__ == module.__name__
        ]
        if not candidates:
            print(f"Error: No classes found in '{path_or_module}'. "
                  "Specify a class name with 'path/to/file.py:ClassName'.")
            sys.exit(1)
        if len(candidates) > 1:
            names = ', '.join(c.__name__ for c in candidates)
            print(f"Error: Multiple classes found in '{path_or_module}' ({names}). "
                  "Specify one with 'path/to/file.py:ClassName'.")
            sys.exit(1)
        cls = candidates[0]

    try:
        return cls(**(kwargs or {}))
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error: Could not instantiate simulation class '{cls.__name__}': {e}")
        sys.exit(1)


def main():
    """
    main function
    """
    args, _ = ScenarioExecution.get_arg_parser().parse_known_args(sys.argv[1:])
    simulation = None
    if args.simulation:
        simulation = _load_simulation(args.simulation)
    try:
        scenario_execution = ScenarioExecution(debug=args.debug,
                                               log_model=args.log_model,
                                               live_tree=args.live_tree,
                                               scenario_file=args.scenario,
                                               output_dir=args.output_dir,
                                               dry_run=args.dry_run,
                                               render_dot=args.dot,
                                               tick_period=args.step_duration,
                                               scenario_parameter_file=args.scenario_parameter_file,
                                               create_scenario_parameter_file_template=args.create_scenario_parameter_file_template,
                                               post_run=args.post_run,
                                               simulation=simulation,
                                               output_result_per_scenario=args.output_result_per_scenario)
    except ValueError as e:
        print(f"Error while initializing: {e}")
        sys.exit(1)
    result = scenario_execution.parse()
    if result and not args.dry_run and not args.create_scenario_parameter_file_template:
        scenario_execution.run()
    if args.create_scenario_parameter_file_template:
        result = True
    else:
        result = scenario_execution.process_results()

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
