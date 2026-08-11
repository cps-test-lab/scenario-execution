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

"""The standalone MCP server registers scenario_execution.introspection's own functions,
unchanged -- this confirms the registration, not the introspection logic itself (covered
by scenario_execution's own test_introspection.py)."""

import asyncio
import json
import unittest

from scenario_execution_mcp.mcp_server import create_server


def _run(coro):
    return asyncio.run(coro)


class TestMcpServer(unittest.TestCase):

    def test_all_four_tools_are_registered(self):
        async def _names():
            return {t.name for t in await create_server().list_tools()}

        names = _run(_names())
        self.assertEqual(
            names, {"list_actions", "get_action_details", "describe_scenario", "validate"})

    def test_list_actions_reflects_the_real_environment(self):
        """Mirrors test_introspection.py's own TestListActions assertion -- same function,
        reached through the MCP tool call this time, not a direct Python import."""
        async def _call():
            server = create_server()
            result = await server.call_tool("list_actions", {})
            return result

        result = _run(_call())
        catalog = json.loads(result.content[0].text)
        log = next((a for a in catalog["actions"] if a["name"] == "log"), None)
        self.assertIsNotNone(log, "expected the 'log' action from osc.helpers")
        self.assertTrue(log["resolvable"])

    def test_get_action_details_unknown_name_is_error(self):
        async def _call():
            server = create_server()
            return await server.call_tool("get_action_details", {"name": "nope_xyz"})

        result = _run(_call())
        payload = json.loads(result.content[0].text)
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
