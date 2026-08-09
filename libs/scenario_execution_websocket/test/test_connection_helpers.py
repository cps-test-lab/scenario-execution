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

import operator
import unittest

from scenario_execution_websocket.connection import (
    to_rosbridge_type,
    parse_dict_value,
    parse_call_data,
    parse_scalar,
    get_comparison_operator,
    get_member,
)


class TestConnectionHelpers(unittest.TestCase):
    # pylint: disable=missing-function-docstring,missing-class-docstring

    def test_to_rosbridge_type_dotted(self):
        self.assertEqual(to_rosbridge_type('std_msgs.msg.String'), 'std_msgs/msg/String')
        self.assertEqual(to_rosbridge_type('example_interfaces.action.Fibonacci'),
                         'example_interfaces/action/Fibonacci')

    def test_to_rosbridge_type_slash_passthrough(self):
        self.assertEqual(to_rosbridge_type('std_msgs/msg/String'), 'std_msgs/msg/String')

    def test_to_rosbridge_type_errors(self):
        with self.assertRaises(ValueError):
            to_rosbridge_type('')
        with self.assertRaises(ValueError):
            to_rosbridge_type('std_msgs.msg/String')

    def test_parse_dict_value(self):
        self.assertEqual(parse_dict_value('{"data": "hi"}'), {'data': 'hi'})
        self.assertEqual(parse_dict_value({'data': 'hi'}), {'data': 'hi'})
        with self.assertRaises(ValueError):
            parse_dict_value('123')  # not a dict
        with self.assertRaises(ValueError):
            parse_dict_value(123)

    def test_parse_call_data(self):
        self.assertEqual(parse_call_data(''), {})
        self.assertEqual(parse_call_data(None), {})
        self.assertEqual(parse_call_data('{"order": 5}'), {'order': 5})
        self.assertEqual(parse_call_data({'order': 5}), {'order': 5})

    def test_parse_scalar(self):
        self.assertEqual(parse_scalar('5'), 5)
        self.assertEqual(parse_scalar('5.5'), 5.5)
        self.assertEqual(parse_scalar('True'), True)
        self.assertEqual(parse_scalar('plain'), 'plain')  # falls back to string
        self.assertEqual(parse_scalar(7), 7)

    def test_get_comparison_operator(self):
        self.assertIs(get_comparison_operator(('eq',)), operator.eq)
        self.assertIs(get_comparison_operator(('lt',)), operator.lt)
        self.assertIs(get_comparison_operator(('gt', 5)), operator.gt)
        with self.assertRaises(ValueError):
            get_comparison_operator(('bogus',))

    def test_get_member(self):
        msg = {'data': 'hi', 'header': {'frame_id': 'map'}}
        self.assertEqual(get_member(msg, ''), msg)
        self.assertEqual(get_member(msg, 'data'), 'hi')
        self.assertEqual(get_member(msg, 'header.frame_id'), 'map')
        with self.assertRaises(KeyError):
            get_member(msg, 'missing')


if __name__ == '__main__':
    unittest.main()
