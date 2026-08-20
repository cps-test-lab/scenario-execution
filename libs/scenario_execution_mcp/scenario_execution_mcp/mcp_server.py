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

"""A real MCP server for this package's own introspection, needing no particular consumer.

The JSON CLIs (``python -m scenario_execution.introspection ...``,
``python -m scenario_execution.tree_state``) answer from a shell but not from an MCP
client. This registers the exact same functions as MCP tools -- no new logic, just a
second, equally thin adapter.

Runnable via ``python -m scenario_execution_mcp`` or the ``scenario_execution_mcp``
console script (stdio transport), so anyone with a shell in the image can point an MCP
client at it directly -- without this package's own dependents having to have heard of
``fastmcp``, and without a tool on the host that knows how to drive it.
"""

from fastmcp import FastMCP

from scenario_execution.introspection import (describe_scenario, get_action_details,
                                              list_actions, validate)
from scenario_execution.tree_state import tree_state

#: ``tree_state`` is the one runtime question here -- where a *particular execution* has got to,
#: rather than what this environment or this file offers. Registered the same way for the same
#: reason: it is already a plain function returning plain data, so the adapter stays one line.
_TOOLS = [list_actions, get_action_details, describe_scenario, validate, tree_state]


def create_server() -> FastMCP:
    mcp = FastMCP("scenario_execution")
    for fn in _TOOLS:
        mcp.tool()(fn)
    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
