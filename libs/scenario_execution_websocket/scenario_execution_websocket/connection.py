# Copyright (C) 2026 Frederik Pasch
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

"""
Shared rosbridge (roslibpy) helpers used by all rosbridge_* actions.

This module keeps the package ROS-free: it only depends on ``roslibpy`` and the
standard library. A single ``roslibpy.Ros`` connection is shared per
``(host, port)`` so that repeated actions against the same rosbridge server do
not each open their own websocket.
"""

import atexit
import operator
import threading
import time
from ast import literal_eval

import roslibpy

# module-level connection pool, keyed by (host, port)
_connections = {}
_connections_lock = threading.Lock()


def get_connection(host: str, port: int, timeout: float = 10.0) -> roslibpy.Ros:
    """
    Return a connected ``roslibpy.Ros`` for the given host/port, creating and
    connecting it lazily. Connections are cached and reused.

    Raises:
        ConnectionError: if the connection could not be established within
            ``timeout`` seconds.
    """
    key = (host, int(port))
    with _connections_lock:
        ros = _connections.get(key)
        if ros is None:
            ros = roslibpy.Ros(host=host, port=int(port))
            _connections[key] = ros
        if not ros.is_connected:
            # run() is non-blocking: it starts roslibpy's event loop in a
            # background thread and returns immediately.
            ros.run()
        deadline = time.time() + timeout
        while not ros.is_connected and time.time() < deadline:
            time.sleep(0.05)
        if not ros.is_connected:
            raise ConnectionError(
                f"Could not connect to rosbridge at {host}:{port} within {timeout}s.")
        return ros


@atexit.register
def _close_all_connections():
    for ros in _connections.values():
        try:
            if ros.is_connected:
                ros.terminate()
        except Exception:  # pylint: disable=broad-except
            pass


def to_rosbridge_type(type_string: str) -> str:
    """
    Convert an OSC message/service/action type string to the rosbridge form.

    Accepts the scenario_execution_ros convention using ``.`` as separator
    (e.g. ``std_msgs.msg.String``) and returns the rosbridge/ROS form using
    ``/`` (e.g. ``std_msgs/msg/String``). A string that already uses ``/`` is
    passed through unchanged.
    """
    if not type_string:
        raise ValueError("Empty message type.")
    if '.' in type_string and '/' in type_string:
        raise ValueError("Either use '.' or '/' as separator, not both.")
    return type_string.replace('.', '/')


def parse_dict_value(value):
    """
    Parse an OSC ``value`` into a dict suitable for ``roslibpy.Message``.

    Mirrors scenario_execution_ros topic-publish parsing: a dict passes through,
    a string is stripped of escaping backslashes and evaluated with
    ``ast.literal_eval``.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError(f'Expected type "dict" or "str", got {type(value)}.')
    parsed = literal_eval("".join(value.split('\\')))
    if not isinstance(parsed, dict):
        raise ValueError(f'Parsed value needs type "dict", got {type(parsed)}.')
    return parsed


def parse_call_data(data):
    """
    Parse OSC service/action ``data`` into a python object.

    Mirrors scenario_execution_ros service/action parsing (``unicode_escape``
    un-escaping before ``ast.literal_eval``). An empty string yields ``{}``.
    """
    if isinstance(data, dict):
        return data
    if data is None or data == "":
        return {}
    trimmed = data.encode('utf-8').decode('unicode_escape')
    return literal_eval(trimmed)


def parse_scalar(value):
    """
    Parse a parameter value string into a python scalar, falling back to the
    raw string if it is not a python literal (e.g. a bare word).
    """
    if not isinstance(value, str):
        return value
    try:
        return literal_eval(value)
    except (ValueError, SyntaxError):
        return value


_COMPARISON_OPERATORS = {
    'lt': operator.lt,
    'le': operator.le,
    'eq': operator.eq,
    'ne': operator.ne,
    'ge': operator.ge,
    'gt': operator.gt,
}


def get_comparison_operator(operator_val):
    """
    Map an OSC ``comparison_operator`` enum value to the python operator.

    ``operator_val`` is the resolved enum tuple whose first element is the name.
    """
    name = operator_val[0] if isinstance(operator_val, (tuple, list)) else operator_val
    try:
        return _COMPARISON_OPERATORS[name]
    except KeyError as e:
        raise ValueError(f"Invalid comparison_operator: {operator_val}") from e


def get_member(msg, member_name):
    """
    Return a (possibly nested) member of a received rosbridge message dict.

    ``member_name`` uses ``.`` to descend into nested fields. An empty
    ``member_name`` returns the whole message.
    """
    if not member_name:
        return msg
    value = msg
    for part in member_name.split('.'):
        try:
            value = value[part]
        except (KeyError, TypeError) as e:
            raise KeyError(f"invalid member_name '{member_name}'") from e
    return value
