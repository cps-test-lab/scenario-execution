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

import py_trees  # pylint: disable=import-error
import subprocess  # nosec B404
from threading import Thread, Lock
from collections import deque
import signal
from scenario_execution.actions.base_action import BaseAction
import os


def _command_text(command):
    """A command rendered the way a human reads it, for a log line.

    ``command`` is normally a list of argv tokens, but a subclass may not have set it yet, so this
    falls back to ``str()`` rather than assuming ``join()`` applies. Matches how ``ros_launch``
    already reports its command.
    """
    if isinstance(command, (list, tuple)):
        return " ".join(str(part) for part in command)
    return str(command)


class RunProcess(BaseAction):
    """
    Class to execute an process.
    """

    def __init__(self):
        super().__init__()
        self.command = None
        self.wait_for_shutdown = None
        self.shutdown_timeout = None
        self.shutdown_signal = None
        self.executed = False
        self.process = None
        #: The command the currently running process was actually started with. Kept separately from
        #: ``command``, which a re-initialise overwrites before ``update()`` gets to compare them.
        self.started_command = None
        self.log_stdout_thread = None
        self.log_stderr_thread = None
        self.output = deque()
        self.output_lock = Lock()
        self.process_registry = None

    def setup(self, **kwargs):
        self.process_registry = kwargs.get('process_registry')
        has_label = self._model is not None and self._model.name
        if self.process_registry is not None and has_label:
            self.process_registry.register(self.name, self)

    def execute(self, command=None, wait_for_shutdown=True, shutdown_timeout=10, shutdown_signal=("", signal.SIGTERM)):
        self.command = command.split(" ") if isinstance(command, str) else command
        self.wait_for_shutdown = wait_for_shutdown
        self.shutdown_timeout = shutdown_timeout
        self.shutdown_signal = shutdown_signal[1]
        self.executed = False

    def update(self) -> py_trees.common.Status:
        """
        Start/monitor process

        return:
            py_trees.common.Status
        """
        if not self.executed:
            self.executed = True
            # py_trees re-initialises every child that is not RUNNING, and initialise() calls
            # execute(), which re-arms this branch. For an action parked in SUCCESS
            # (wait_for_shutdown: false) that happens on the tick after the root succeeds -- so
            # spawning again here would rebind self.process to the newborn and lose the handle on the
            # real child. shutdown() would then signal the newborn's process group and report success
            # while the real one keeps running, and a simulator that writes its results only on a
            # clean stop is later killed with nothing written. Keep the process we already own.
            if self.process is not None and self.process.poll() is None:
                if self.command != self.started_command:
                    # Not the benign re-initialise: a *different* process was asked for while the
                    # previous one runs. Say so; silently running the old one hides the divergence.
                    self.logger.warning(
                        f"Re-initialised with a different command while still running "
                        f"'{_command_text(self.started_command)}'; keeping it and ignoring "
                        f"'{_command_text(self.command)}'.")
                else:
                    self.logger.debug('Re-initialised while still running; keeping the process.')
                # Deliberately no early return: the checks below are the one place that turns a
                # process state into a status, and on_executed()/the reader threads must not run
                # again for a process that is already going (the on_executed() overrides reset
                # current_state to a *waiting* state, which this process is long past).
            else:
                try:
                    self.process = subprocess.Popen(
                        self.command,
                        start_new_session=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )
                except Exception as e:  # pylint: disable=broad-except
                    self.logger.error(str(e))
                    return py_trees.common.Status.FAILURE
                self.started_command = self.command

                self.feedback_message = f"Executing '{self.command}'"  # pylint: disable= attribute-defined-outside-init
                self.logger.debug(f"Executing '{self.command}'")
                self.on_executed()

                def log_output(out, log_fct, buffer):
                    try:
                        for line in iter(out.readline, b''):
                            msg = line.decode().strip()
                            if log_fct:
                                log_fct(msg)
                            with self.output_lock:
                                buffer.append(msg)
                        out.close()
                    except ValueError:
                        pass
                    except Exception as e:  # pylint: disable=broad-except
                        self.logger.error(f"Error while logging output: {e}")
                self.log_stdout_thread = Thread(target=log_output, args=(
                    self.process.stdout, self.get_logger_stdout(), self.output))
                self.log_stdout_thread.daemon = True  # die with the program
                self.log_stdout_thread.start()

                self.log_stderr_thread = Thread(target=log_output, args=(
                    self.process.stderr, self.get_logger_stderr(), self.output))
                self.log_stderr_thread.daemon = True  # die with the program
                self.log_stderr_thread.start()

        if self.process is None:
            self.process = None
            return py_trees.common.Status.FAILURE

        ret = self.process.poll()

        if ret is None:
            return self.check_running_process()
        else:
            return self.on_process_finished(ret)

    def get_logger_stdout(self):
        """
        get logger for stderr messages
        """
        return self.logger.info

    def get_logger_stderr(self):
        """
        get logger for stderr messages
        """
        return self.logger.error

    def check_running_process(self):
        """
        hook to check running process

        return:
            py_trees.common.Status
        """
        if self.wait_for_shutdown:
            return py_trees.common.Status.RUNNING
        else:
            return py_trees.common.Status.SUCCESS

    def on_process_finished(self, ret):
        """
        hook to check finished process

        return:
            py_trees.common.Status
        """
        if ret == 0:
            self.feedback_message = f"Successfully executed '{self.command}'"  # pylint: disable= attribute-defined-outside-init
            return py_trees.common.Status.SUCCESS
        else:
            self.feedback_message = f"Execution of '{self.command}' failed with {ret}"  # pylint: disable= attribute-defined-outside-init
            return py_trees.common.Status.FAILURE

    def on_executed(self):
        """
        hook for subclassed
        """
        pass

    def get_output_snapshot(self):
        """
        Return a non-mutating snapshot of the captured process output.
        """
        with self.output_lock:
            return list(self.output)

    def is_output_complete(self):
        """
        Return whether the process has finished and both output readers are done.
        """
        if self.process is None or self.process.poll() is None:
            return False
        stdout_done = self.log_stdout_thread is None or not self.log_stdout_thread.is_alive()
        stderr_done = self.log_stderr_thread is None or not self.log_stderr_thread.is_alive()
        return stdout_done and stderr_done

    def set_command(self, command):
        self.command = command

    def get_command(self):
        return self.command

    def shutdown(self):
        if self.process is None:
            return

        ret = self.process.poll()
        if ret is None:
            # kill running process
            self.logger.info(f'Sending {signal.Signals(self.shutdown_signal).name} to process...')
            pgid = os.getpgid(self.process.pid)
            os.killpg(pgid, self.shutdown_signal)
            if self.process.poll() is None:
                self.logger.info(f"Waiting {self.shutdown_timeout}s for process to finish...")
                try:
                    self.process.wait(self.shutdown_timeout)
                    self.logger.info('Process finished.')
                except subprocess.TimeoutExpired:
                    self.logger.info('Sending SIGKILL to process...')
                    os.killpg(pgid, signal.SIGKILL)
                    self.process.wait()
                    self.logger.info('Process finished.')
            else:
                self.logger.info('Process finished.')
