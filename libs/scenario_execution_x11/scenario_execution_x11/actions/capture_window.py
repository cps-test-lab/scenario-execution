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

from enum import Enum
import py_trees
import os
from scenario_execution.actions.base_action import ActionError
from scenario_execution.actions.run_process import RunProcess
from Xlib.display import Display
from Xlib import error


class CaptureWindowState(Enum):
    IDLE = 1
    WAITING_FOR_WINDOW = 2
    CAPTURING = 3
    DONE = 11
    FAILURE = 12


class CaptureWindow(RunProcess):

    def __init__(self):
        super().__init__()
        self.current_state = None
        self.output_dir = "."
        self.video_size = None
        self.window_name = None
        self.root_display = None

    def setup(self, **kwargs):
        if "DISPLAY" not in os.environ:
            raise ActionError("capture_window() requires environment variable 'DISPLAY' to be set.", action=self)

        if kwargs['output_dir']:
            if not os.path.exists(kwargs['output_dir']):
                raise ActionError(
                    f"Specified destination dir '{kwargs['output_dir']}' does not exist", action=self)
            self.output_dir = kwargs['output_dir']

        self.root_display = Display().screen().root

    def execute(self, window_name: str, output_filename: str, frame_rate: float):  # pylint: disable=arguments-differ
        super().execute(None, wait_for_shutdown=True)
        self.window_name = window_name
        self.frame_rate = frame_rate
        self.output_filename = output_filename
        self.current_state = CaptureWindowState.WAITING_FOR_WINDOW

    def update(self) -> py_trees.common.Status:
        if self.current_state == CaptureWindowState.WAITING_FOR_WINDOW:
            self.feedback_message = f"Waiting for window {self.window_name}..."  # pylint: disable= attribute-defined-outside-init
                
            video_size = self.get_window(self.root_display, self.window_name, "")
            if video_size is not None:
                self.video_size = video_size
                self.feedback_message = f"Found window (size {self.video_size})..."  # pylint: disable= attribute-defined-outside-init
                self.current_state = CaptureWindowState.IDLE

                cmd = ["ffmpeg",
                    "-video_size", f"{self.video_size[2]}x{self.video_size[3]}",
                    "-f", "x11grab",
                    "-draw_mouse", "0",
                    "-framerate", str(self.frame_rate),
                    "-i", f"{os.environ["DISPLAY"]}+{self.video_size[0]},{self.video_size[1]}",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-f", "mp4",
                    "-nostdin",
                    "-y", os.path.join(self.output_dir, self.output_filename)]
                self.set_command(cmd)
            return py_trees.common.Status.RUNNING
        else:
            return super().update()

    def get_logger_stdout(self):
        return self.logger.debug

    def get_logger_stderr(self):
        return self.logger.debug

    def on_executed(self):
        self.current_state = CaptureWindowState.CAPTURING
        self.feedback_message = f"Capturing window..."  # pylint: disable= attribute-defined-outside-init

    def on_process_finished(self, ret):
        if self.current_state == CaptureWindowState.CAPTURING:
            self.feedback_message = f"Capturing window failed. {self.output[-1]}"  # pylint: disable= attribute-defined-outside-init
            return py_trees.common.Status.FAILURE
        return py_trees.common.Status.SUCCESS



    def get_window(self, window, window_name, indent):
        children = window.query_tree().children
        splits = window_name.split('/')
        if splits:
            for w in children:
                try:
                    if len(splits) == 1:
                        name = w.get_wm_name()
                        wm_class = w.get_wm_class()
                        if (name is not None and splits[0] in str(name)) or (wm_class is not None and splits[0] in wm_class):
                            geom = w.get_geometry()
                            window_pos = (geom.x, geom.y, geom.width, geom.height)
                            return window_pos
                        else:
                            continue
                    else:
                        name = w.get_wm_name()
                        wm_class = w.get_wm_class()
                        if (name is not None and splits[0] in str(name)) or (wm_class is not None and splits[0] in wm_class):
                            return self.get_window(w, "/".join(splits[1:]), indent + "  ")
                        else:
                            found = self.get_window(w, window_name, indent + "  ")
                            if found:
                                geom = w.get_geometry()
                                current_window_pos = (geom.x, geom.y, geom.width, geom.height)
                                return (current_window_pos[0] + found[0], 
                                        current_window_pos[1] + found[1], 
                                        found[2], 
                                        found[3])
                except (error.BadWindow, error.XError):
                    continue
        return None
