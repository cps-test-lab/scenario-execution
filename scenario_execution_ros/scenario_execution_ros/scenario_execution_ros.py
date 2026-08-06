# Copyright (C) 2024 Intel Corporation
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

""" Main entry for scenario_execution_ros """
import sys
import time
import rclpy  # pylint: disable=import-error
import py_trees_ros
from py_trees_ros_interfaces.srv import OpenSnapshotStream
from scenario_execution import ScenarioExecution, ShutdownHandler
from scenario_execution.scenario_execution_base import _load_simulation, _build_reset_kwargs
from scenario_execution.simulation import Clock
from .logging_ros import RosLogger
from .marker_handler import MarkerHandler


class RosClock(Clock):
    """The ROS time source, as a scenario_execution Clock.

    Implements the interface the framework already defines rather than adding a
    ROS-specific path: with ``use_sim_time`` this is the /clock timeline, so a
    behaviour-tree log recorded through it lines up with everything else in the run.
    """

    def __init__(self, node):
        self._node = node
        self._start = node.get_clock().now().nanoseconds / 1e9

    def now(self) -> float:
        return self._node.get_clock().now().nanoseconds / 1e9 - self._start


class InterruptibleBehaviourTree(py_trees_ros.trees.BehaviourTree):
    """A py_trees_ros tree whose ``interrupt()`` actually stops the ticking.

    py_trees' ``interrupt()`` sets ``interrupt_tick_tocking``, which its own blocking ``tick_tock``
    loop checks every iteration. py_trees_ros re-implements ``tick_tock`` on an rclpy timer whose
    callback never reads that flag, so ``interrupt()`` is a no-op here and the timer is stopped only
    by ``shutdown()``.

    That gap loses run artifacts. ``on_scenario_shutdown`` calls ``interrupt()`` and then schedules
    ``shutdown()`` as an executor task, so between the two the timer keeps firing; py_trees
    re-initialises every child that is not RUNNING, and an action parked in SUCCESS
    (``wait_for_shutdown: false``) is re-``execute()``d. For ``ros_launch`` that used to spawn a
    second ``ros2 launch``, which ``shutdown()`` then killed instead of the real one -- leaving the
    simulator orphaned and its recording and run capture never written.

    ``shutdown()`` cancels and destroys the same timer afterwards; cancelling twice is harmless, and
    ``timer`` is ``None`` until ``tick_tock()`` runs, so interrupting before then is a no-op.
    """

    def interrupt(self):
        if self.timer is not None:
            self.timer.cancel()
        super().interrupt()


class ROSScenarioExecution(ScenarioExecution):
    """
    Class for scenario execution using ROS2 as middleware
    """

    def __init__(self) -> None:
        self.node = rclpy.create_node(node_name="scenario_execution_ros")
        self.marker_handler = MarkerHandler(self.node)
        self.shutdown_task = None

        # parse from commandline
        args_without_ros = rclpy.utilities.remove_ros_args(sys.argv[1:])
        arg_parser = ScenarioExecution.get_arg_parser()
        arg_parser.add_argument('--snapshot-period', type=float, help='How often to publish behavior tree snapshots (default: only on status change)', default=sys.float_info.max)
        args, _ = arg_parser.parse_known_args(args_without_ros)

        debug = args.debug
        log_model = args.log_model
        live_tree = args.live_tree
        scenario = args.scenario
        output_dir = args.output_dir
        self.dry_run = args.dry_run
        self.render_dot = args.dot
        self.scenario_parameter_file = args.scenario_parameter_file
        self.create_scenario_parameter_file_template = args.create_scenario_parameter_file_template
        self.post_run = args.post_run
        self.snapshot_period = args.snapshot_period
        self.output_result_per_scenario = args.output_result_per_scenario
        bt_log = args.bt_log

        # override commandline by ros parameters
        self.node.declare_parameter('debug', False)
        self.node.declare_parameter('log_model', False)
        self.node.declare_parameter('live_tree', False)
        self.node.declare_parameter('output_dir', "")
        self.node.declare_parameter('scenario', "")
        self.node.declare_parameter('dry_run', False)
        self.node.declare_parameter('dot', False)
        self.node.declare_parameter('scenario_parameter_file', "")
        self.node.declare_parameter('create_scenario_parameter_file_template', False)
        self.node.declare_parameter('post_run', [""])
        self.node.declare_parameter('snapshot_period', 1.0)
        self.node.declare_parameter('bt_log', False)

        if self.node.get_parameter('debug').value:
            debug = self.node.get_parameter('debug').value
        if self.node.get_parameter('log_model').value:
            log_model = self.node.get_parameter('log_model').value
        if self.node.get_parameter('live_tree').value:
            live_tree = self.node.get_parameter('live_tree').value
        if self.node.get_parameter('scenario').value:
            scenario = self.node.get_parameter('scenario').value
        if self.node.get_parameter('output_dir').value:
            output_dir = self.node.get_parameter('output_dir').value
        if self.node.get_parameter('dry_run').value:
            self.dry_run = self.node.get_parameter('dry_run').value
        if self.node.get_parameter('dot').value:
            self.render_dot = self.node.get_parameter('dot').value
        if self.node.get_parameter('scenario_parameter_file').value:
            self.scenario_parameter_file = self.node.get_parameter('scenario_parameter_file').value
        if self.node.get_parameter('create_scenario_parameter_file_template').value:
            self.create_scenario_parameter_file_template = self.node.get_parameter('create_scenario_parameter_file_template').value
        post_run_param = [v for v in self.node.get_parameter('post_run').value if v]
        if post_run_param:
            self.post_run = post_run_param
        if self.node.get_parameter('snapshot_period').value:
            self.snapshot_period = self.node.get_parameter('snapshot_period').value
        if self.node.get_parameter('bt_log').value:
            bt_log = self.node.get_parameter('bt_log').value
        self.logger = RosLogger('scenario_execution_ros', debug)
        # Optional step-based SimulationInterface (--simulation module:Class). The base ROS runner
        # historically ignored it; _run_single_scenario() below now drives its
        # setup/reset/step/shutdown inside the ROS spin loop (see run() docstring).
        simulation = _load_simulation(args.simulation) if getattr(args, 'simulation', None) else None
        super().__init__(debug=debug,
                         log_model=log_model,
                         live_tree=live_tree,
                         scenario_file=scenario,
                         output_dir=output_dir,
                         dry_run=self.dry_run,
                         render_dot=self.render_dot,
                         scenario_parameter_file=self.scenario_parameter_file,
                         create_scenario_parameter_file_template=self.create_scenario_parameter_file_template,
                         post_run=self.post_run,
                         output_result_per_scenario=self.output_result_per_scenario,
                         simulation=simulation,
                         bt_log=bt_log,
                         logger=self.logger)

    def setup_behaviour_tree(self, tree):
        """
        Setup the behaviour tree
        Using py_trees_ros to get a node handle on ROS2 and tick in syn with ROS2

        Args:
            tree [py_trees.behaviour.Behaviour]: root of the behaviour tree

        return:
            InterruptibleBehaviourTree
        """
        return InterruptibleBehaviourTree(tree)

    def post_setup(self):
        request = OpenSnapshotStream.Request()
        request.topic_name = "/scenario_execution/snapshots"
        request.parameters.snapshot_period = self.snapshot_period
        request.parameters.blackboard_data = True
        response = OpenSnapshotStream.Response()
        self.behaviour_tree._open_snapshot_stream(request, response)  # pylint: disable=protected-access

    SHUTDOWN_TIMEOUT = 30.0  # seconds to wait for async shutdown operations (e.g. goal cancellations)

    def run(self) -> bool:
        """Execute every scenario in ``self.scenarios_list`` sequentially.

        A single ROS executor and node are kept alive across all scenarios; only
        the behaviour tree is rebuilt (and torn down) per scenario. ROS is shut
        down once, after the last scenario. With multiple scenarios (e.g. one per
        document of a multi-document ``--scenario-parameter-file``) each result is
        written into its own ``_output_dir`` by :meth:`process_results`.

        When a step-based ``--simulation`` (SimulationInterface) is given, each
        scenario additionally sets it up, resets it with the scenario parameters,
        ticks ``simulation.step()`` inside the ROS spin loop, and shuts it down.
        Unlike the non-ROS ``run_with_simulation`` (which the simulation drives
        exclusively), here ROS behaviours run the scenario while the simulation
        advances time (a simulation that publishes ``/clock`` becomes the time
        source; other nodes run ``use_sim_time``).
        """
        self._aborted = False
        # The node created in __init__ is only needed to read ROS parameters; each
        # scenario gets its own fresh node below, so release this one.
        try:
            self.node.destroy_node()
        except Exception as e:  # pylint: disable=broad-except
            self.logger.debug(f"Exception destroying bootstrap node: {e}")

        try:
            multiple_scenarios = len(self.scenarios_list) > 1
            for tree, params, scenario_output_dir_override in self.scenarios_list:
                effective_output_dir = self._resolve_scenario_output_dir(
                    tree.name, scenario_output_dir_override, multiple_scenarios)
                if effective_output_dir is None and multiple_scenarios and self.output_dir:
                    # Directory creation failed; failure already recorded.
                    continue
                self._run_single_scenario(tree, effective_output_dir, params)
                if self._aborted:
                    break
        finally:
            rclpy.shutdown()

    def _run_single_scenario(self, tree, effective_output_dir, scenario_params=None):
        """Set up, tick and tear down one scenario's behaviour tree.

        Each scenario runs on its OWN ROS node and executor: py_trees_ros adopts
        the node it is given and destroys it on ``shutdown()``, so the node cannot
        be shared across scenarios.

        If a step-based ``--simulation`` is configured it is set up and reset for
        this scenario, stepped once per spin-loop iteration (paced to realtime),
        and shut down afterwards -- so the simulation advances alongside the ROS
        behaviours that drive it.
        """
        # Reset per-scenario async-shutdown state so the previous scenario's
        # tasks/futures do not leak into this one.
        self.shutdown_task = None
        ShutdownHandler.get_instance().futures.clear()

        self.node = rclpy.create_node(node_name="scenario_execution_ros")
        self.marker_handler = MarkerHandler(self.node)
        executor = rclpy.executors.MultiThreadedExecutor()
        executor.add_node(self.node)

        # Optional step-based SimulationInterface: build + reset it for this scenario. A simulation
        # that publishes /clock on step() becomes the time source; other nodes run use_sim_time.
        sim_dt = None
        if self.simulation is not None:
            try:
                self.simulation.setup(logger=self.logger, output_dir=effective_output_dir,
                                      tick_period=self.tick_period)
                self.simulation.reset(**_build_reset_kwargs(self.simulation, scenario_params or {}))
                sim_dt = self.simulation.dt
            except Exception as e:  # pylint: disable=broad-except
                self.on_scenario_shutdown(False, "Simulation setup failed", f"{e}")
                self._shutdown_simulation()
                try:
                    self.node.destroy_node()
                except Exception:  # pylint: disable=broad-except
                    pass
                return

        try:
            try:
                # sim_clock (not clock) so the behaviour-tree log gets ROS time without
                # also retargeting ClockTimer/ClockTimeout, which would change when
                # timeouts fire in every existing scenario.
                self.setup(tree, current_output_dir=effective_output_dir,
                           node=self.node, marker_handler=self.marker_handler,
                           sim_clock=RosClock(self.node))
            except Exception as e:  # pylint: disable=broad-except
                self.on_scenario_shutdown(False, "Setup failed", f"{e}")
                return

            try:
                self.behaviour_tree.tick_tock(period_ms=1000. * self.tick_period)
                shutdown_done_time = None
                next_step = time.perf_counter()
                while rclpy.ok():
                    try:
                        if self.simulation is not None:
                            # Pace stepping to realtime (v1): step only once wall time has caught up,
                            # and spin ROS in the gap so behaviour action feedback keeps flowing.
                            # For faster-than-realtime, drop the `now >= next_step` gate.
                            now = time.perf_counter()
                            if now >= next_step:
                                self.simulation.step()
                                next_step += sim_dt
                            executor.spin_once(
                                timeout_sec=max(min(next_step - time.perf_counter(), sim_dt), 0.0))
                        else:
                            executor.spin_once(timeout_sec=self.tick_period)
                    except KeyboardInterrupt:
                        self._aborted = True
                        self.on_scenario_shutdown(False, "Aborted")

                    if self.shutdown_task is not None and self.shutdown_task.done():
                        shutdown_handler = ShutdownHandler.get_instance()
                        if shutdown_handler.is_done():
                            self.logger.info("Shutting down finished.")
                            break
                        if shutdown_done_time is None:
                            shutdown_done_time = time.monotonic()
                        elif time.monotonic() - shutdown_done_time > self.SHUTDOWN_TIMEOUT:
                            self.logger.warning(
                                f"Shutdown timed out after {self.SHUTDOWN_TIMEOUT}s waiting for async operations.")
                            break
            except Exception as e:  # pylint: disable=broad-except
                self.on_scenario_shutdown(False, "Run failed", f"{e}")
            finally:
                # ensure behaviour tree threads are stopped before the next scenario
                self._robust_tree_shutdown()
                self._shutdown_simulation()
        finally:
            # py_trees_ros may already have destroyed the node during shutdown;
            # destroy_node() is idempotent-safe here (errors are ignored).
            try:
                self.node.destroy_node()
            except Exception as e:  # pylint: disable=broad-except
                self.logger.debug(f"Exception destroying scenario node: {e}")

    def _shutdown_simulation(self):
        """Shut down the step-based simulation for the current scenario, if any."""
        if self.simulation is None:
            return
        try:
            self.simulation.shutdown()
        except Exception as e:  # pylint: disable=broad-except
            self.logger.error(f"Simulation shutdown error: {e}")

    def shutdown(self):
        self.logger.info("Shutting down...")
        self._robust_tree_shutdown()

    def _robust_tree_shutdown(self):
        """Shut down the tree, guaranteeing every behaviour gets torn down.

        First call the tree's own ``shutdown()``: besides crawling the behaviours
        this also stops the tick-tock timer, so actions are not re-initialised
        mid-teardown (otherwise an active ``bag_record`` would be re-``execute()``d
        and delete its just-recorded bag). py_trees' crawl, however, aborts as soon
        as one behaviour's ``shutdown()`` raises, which could leave later behaviours
        (e.g. a recording ``bag_record``) un-torn-down and leak into the next
        scenario. So follow up with an isolated per-node pass that catches
        exceptions individually; our actions' ``shutdown()`` are idempotent, so the
        repeated call on already-stopped behaviours is a no-op.
        """
        try:
            self.behaviour_tree.shutdown()
        except (AttributeError, RuntimeError) as e:
            self.logger.debug(f"Exception during tree shutdown: {e}")
        root = getattr(self.behaviour_tree, 'root', None)
        if root is None:
            return
        for node in root.iterate():
            try:
                node.shutdown()
            except Exception as e:  # pylint: disable=broad-except
                self.logger.warning(f"Exception during shutdown of '{node.name}': {e}")

    def on_scenario_shutdown(self, result, failure_message="", failure_output=""):
        if self.shutdown_requested:
            return
        super().on_scenario_shutdown(result, failure_message, failure_output)
        self.shutdown_task = self.node.executor.create_task(self.shutdown)


def main():
    """
    main function
    """
    try:
        rclpy.init(args=sys.argv)
        rclpy.uninstall_signal_handlers()
        scenario_execution_ros = ROSScenarioExecution()
    except Exception as e:  # pylint: disable=broad-except
        print(f"Error while initializing: {e}")
        sys.exit(1)

    result = scenario_execution_ros.parse()

    if result and not scenario_execution_ros.dry_run and not scenario_execution_ros.create_scenario_parameter_file_template:
        scenario_execution_ros.run()
    if scenario_execution_ros.create_scenario_parameter_file_template:
        result = True
    else:
        result = scenario_execution_ros.process_results()
    rclpy.try_shutdown()
    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
