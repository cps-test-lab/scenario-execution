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

import py_trees
import psutil
import os
import time
from threading import Thread, Event
from scenario_execution.actions.base_action import BaseAction
from scenario_execution.scenario_execution_base import ScenarioExecutionConfig


class MonitorResources(BaseAction):
    """
    Monitor CPU and memory usage and write to CSV file
    """

    def __init__(self, file_name: str, log_per_process: bool = False):
        super().__init__()
        self.file_name = file_name
        self.log_per_process = log_per_process
        self.monitor_thread = None
        self.stop_event = Event()
        self.csv_file = None
        self.process = None
        self.monitoring_started = False
        self.tracked_processes = {}  # PID -> psutil.Process mapping for CPU measurement tracking
        output_dir = ScenarioExecutionConfig().output_directory
        if output_dir is None:
            self.feedback_message = "Output directory not configured"
            raise ValueError("Output directory not configured for resource monitoring")
        self.csv_file = os.path.join(output_dir, self.file_name)

    def execute(self):
        """
        Initialize the action with the file name
        """
        # Get the current process
        self.process = psutil.Process()
        
        # Prime the CPU measurement (first call returns 0.0)
        self.process.cpu_percent(interval=None)
        self.tracked_processes[self.process.pid] = self.process
        
        # Initialize CSV file with header
        try:
            with open(self.csv_file, 'w') as f:
                if self.log_per_process:
                    f.write("timestamp,pid,name,cpu_usage,mem_usage\n")
                else:
                    f.write("timestamp,cpu_usage,mem_usage\n")
        except Exception as e:
            self.feedback_message = f"Failed to create CSV file: {e}"
            raise

    def update(self) -> py_trees.common.Status:
        """
        Start monitoring thread on first update, then keep running
        """
        if not self.monitoring_started:
            self.monitoring_started = True
            self.stop_event.clear()
            self.monitor_thread = Thread(target=self._monitor_loop, daemon=False)
            self.monitor_thread.start()
            self.feedback_message = f"Monitoring resources to {self.file_name}..."
            self.logger.info(f"Started resource monitoring to {self.csv_file}")
        
        # Keep running until cancelled
        return py_trees.common.Status.RUNNING

    def _monitor_loop(self):
        """
        Monitoring loop that runs in a separate thread
        """
        try:
            while not self.stop_event.is_set():
                timestamp = time.time()
                
                try:
                    if self.log_per_process:
                        # Log each process individually
                        lines = []
                        
                        # Main process
                        try:
                            cpu = self.process.cpu_percent(interval=None)
                            mem = self.process.memory_info().rss
                            name = self.process.name()
                            lines.append(f"{timestamp},{self.process.pid},{name},{cpu},{mem}\n")
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        
                        # Child processes - discover current children
                        try:
                            # Use dict for lookup, keeps process objects consistent for cpu_percent
                            current_children = self.process.children(recursive=True)
                            
                            # Update tracked processes with new children
                            current_pids = set()
                            for child in current_children:
                                pid = child.pid
                                current_pids.add(pid)
                                if pid not in self.tracked_processes:
                                    try:
                                        # Prime new process
                                        child.cpu_percent(interval=None)
                                        self.tracked_processes[pid] = child
                                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                                        pass
                            
                            # Clean up dead processes
                            # Create a list of keys to safely modify the dict during iteration if needed (or just use list comprehension)
                            for pid in list(self.tracked_processes.keys()):
                                if pid not in current_pids and pid != self.process.pid:
                                    del self.tracked_processes[pid]
                            
                            # Gather stats using the CACHED process objects
                            # This ensures cpu_percent() works correctly (diff against last call on same object)
                            for pid, proc in self.tracked_processes.items():
                                if pid == self.process.pid:
                                    continue
                                try:
                                    cpu = proc.cpu_percent(interval=None)
                                    mem = proc.memory_info().rss
                                    name = proc.name()
                                    lines.append(f"{timestamp},{pid},{name},{cpu},{mem}\n")
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    # Process might have died during this split second
                                    pass
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        
                        # Write all lines at once
                        with open(self.csv_file, 'a') as f:
                            f.writelines(lines)
                    else:
                        # Log aggregated totals
                        cpu_percent = self.process.cpu_percent(interval=None)
                        mem_info = self.process.memory_info()
                        mem_usage = mem_info.rss  # Resident Set Size in bytes
                        
                        # Include all child processes
                        try:
                            children = self.process.children(recursive=True)
                            for child in children:
                                try:
                                    cpu_percent += child.cpu_percent(interval=None)
                                    mem_usage += child.memory_info().rss
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    # Child process may have terminated or we don't have access
                                    continue
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                        
                        # Write to CSV file
                        with open(self.csv_file, 'a') as f:
                            f.write(f"{timestamp},{cpu_percent},{mem_usage}\n")
                    
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    self.logger.warning(f"Error accessing process information: {e}")
                except Exception as e: # pylint: disable=road-exception-caught
                    self.logger.error(f"Error in monitoring loop: {e}")
                
                # Wait for 1 second or until stop event is set
                if self.stop_event.wait(1.0):
                    break
                    
        except Exception as e: # pylint: disable=road-exception-caught
            self.logger.error(f"Critical error in monitoring thread: {e}")
        finally:
            self.logger.debug("Resource monitoring thread stopped")

    def shutdown(self):
        """
        Stop the monitoring thread on shutdown
        """
        if self.monitoring_started and self.monitor_thread is not None:
            self.logger.debug("Stopping resource monitoring thread...")
            self.stop_event.set()
            self.monitor_thread.join(timeout=5.0)
            if self.monitor_thread.is_alive():
                self.logger.warning("Monitoring thread did not stop within timeout")
            else:
                self.logger.debug("Resource monitoring thread stopped successfully")
