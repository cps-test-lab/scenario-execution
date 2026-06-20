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
from .logging_ros import RosLogger
from .marker_handler import MarkerHandler


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
        arg_parser.add_argument(
            '--snapshot-period', type=float, help='How often to publish behavior tree snapshots (default: only on status change)', default=sys.float_info.max
        )
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
        self.logger = RosLogger('scenario_execution_ros', debug)
        super().__init__(
            debug=debug,
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
            logger=self.logger,
        )

    def setup_behaviour_tree(self, tree):
        """
        Setup the behaviour tree
        Using py_trees_ros to get a node handle on ROS2 and tick in syn with ROS2

        Args:
            tree [py_trees.behaviour.Behaviour]: root of the behaviour tree

        return:
            py_trees_ros.trees.BehaviourTree
        """
        return py_trees_ros.trees.BehaviourTree(tree)

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
            for tree, _params, scenario_output_dir_override in self.scenarios_list:
                effective_output_dir = self._resolve_scenario_output_dir(tree.name, scenario_output_dir_override, multiple_scenarios)
                if effective_output_dir is None and multiple_scenarios and self.output_dir:
                    # Directory creation failed; failure already recorded.
                    continue
                self._run_single_scenario(tree, effective_output_dir)
                if self._aborted:
                    break
        finally:
            rclpy.shutdown()

    def _run_single_scenario(self, tree, effective_output_dir):
        """Set up, tick and tear down one scenario's behaviour tree.

        Each scenario runs on its OWN ROS node and executor: py_trees_ros adopts
        the node it is given and destroys it on ``shutdown()``, so the node cannot
        be shared across scenarios.
        """
        # Reset per-scenario async-shutdown state so the previous scenario's
        # tasks/futures do not leak into this one.
        self.shutdown_task = None
        ShutdownHandler.get_instance().futures.clear()

        self.node = rclpy.create_node(node_name="scenario_execution_ros")
        self.marker_handler = MarkerHandler(self.node)
        executor = rclpy.executors.MultiThreadedExecutor()
        executor.add_node(self.node)

        try:
            try:
                self.setup(tree, current_output_dir=effective_output_dir, node=self.node, marker_handler=self.marker_handler)
            except Exception as e:  # pylint: disable=broad-except
                self.on_scenario_shutdown(False, "Setup failed", f"{e}")
                return

            try:
                self.behaviour_tree.tick_tock(period_ms=1000.0 * self.tick_period)
                shutdown_done_time = None
                while rclpy.ok():
                    try:
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
                            self.logger.warning(f"Shutdown timed out after {self.SHUTDOWN_TIMEOUT}s waiting for async operations.")
                            break
            except Exception as e:  # pylint: disable=broad-except
                self.on_scenario_shutdown(False, "Run failed", f"{e}")
            finally:
                # ensure behaviour tree threads are stopped before the next scenario
                self._robust_tree_shutdown()
        finally:
            # py_trees_ros may already have destroyed the node during shutdown;
            # destroy_node() is idempotent-safe here (errors are ignored).
            try:
                self.node.destroy_node()
            except Exception as e:  # pylint: disable=broad-except
                self.logger.debug(f"Exception destroying scenario node: {e}")

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
