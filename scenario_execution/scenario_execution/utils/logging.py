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

import time

YELLOW = '\033[33m'
RED = '\033[31m'
RESET = '\033[0m'


class BaseLogger(object):
    """
    Base class for logger for scenario execution
    For different middleware that does not have logger, inherit from this class
    and override the virtual methods

    Args:
        name [str]: name of the logger
    """

    def __init__(self, name: str, debug) -> None:
        self.name = name
        self.log_debug = debug

    def info(self, msg: str) -> None:
        """
        Virtual method to log info

        Args:
            msg [str]: msg to print
        """
        raise NotImplementedError

    def debug(self, msg: str) -> None:
        """
        virtual method to log debug info

        Args:
            msg [str]: msg to print
        """
        raise NotImplementedError

    def warning(self, msg: str) -> None:
        """
        Virtual method to log warning

        Args:
            msg [str]: msg to print
        """
        raise NotImplementedError

    def error(self, msg: str) -> None:
        """
        Virtual method to log error

        Args:
            msg [str]: msg to print
        """
        raise NotImplementedError


class Logger(BaseLogger):
    """
    Class for logger for scenario execution

    Lines are printed as ``[LEVEL] [epoch] [name]: msg``, which is the format the ROS
    logger (``scenario_execution_ros.logging_ros.RosLogger``, via rclpy) already produces.
    The two implementations of this one base class used to disagree -- this one printed
    ``[name] [INFO] msg`` with no timestamp at all -- so whether a scenario's own output
    could be placed in time depended on which middleware happened to be in use. Tooling
    that reads a run's log has one grammar to parse either way now.

    The timestamp is wall-clock epoch seconds, matching rclpy. It is not sim time: a log
    line is an event in the process that printed it, and correlating that with a simulator's
    clock is the reader's job, which cannot be done at all without a wall stamp here.

    The ANSI colour wraps the *message* rather than the whole line, so that the level marker
    stays at the start where a parser (and a human scanning a column) finds it. Leading
    escape bytes would hide the marker behind an anchored match while still looking correct
    on a terminal, which is the kind of breakage nothing reports.
    """

    def _emit(self, level: str, msg: str, colour: str = '') -> None:
        stamp = f'[{level}] [{time.time():.6f}] [{self.name}]: '
        print(f'{stamp}{colour}{msg}{RESET if colour else ""}')

    def info(self, msg: str) -> None:
        """
        Print an info line.

        Args:
            msg [str]: msg to print
        """
        self._emit('INFO', msg)

    def debug(self, msg: str) -> None:
        """
        Print a debug line, when debug logging is enabled.

        Args:
            msg [str]: msg to print
        """
        if self.log_debug:
            self._emit('DEBUG', msg)

    def warning(self, msg: str) -> None:
        """
        Print a warning, with the message in yellow.

        Args:
            msg [str]: msg to print
        """
        self._emit('WARN', msg, YELLOW)

    def error(self, msg: str) -> None:
        """
        Print an error, with the message in red.

        Args:
            msg [str]: msg to print
        """
        self._emit('ERROR', msg, RED)
