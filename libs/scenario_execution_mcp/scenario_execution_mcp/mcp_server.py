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

"""A real MCP server for ``scenario_execution.introspection`` -- for use *without*
robovast at all.

The JSON CLI (``python -m scenario_execution.introspection ...``) answers "what does
this container have" from a shell, but not from an MCP client. This registers the exact
same functions as MCP tools -- no new logic, just a second, equally thin adapter, the
same one-line pattern robovast's own MCP plugins use to register theirs.

Runnable via ``python -m scenario_execution_mcp`` or the ``scenario_execution_mcp``
console script (stdio transport), so anyone with a shell in the image -- not just
robovast, and not needing this package's own dependents to have ever heard of
``fastmcp`` -- can point an MCP client at it directly.
"""

from fastmcp import FastMCP

from scenario_execution.introspection import (describe_scenario, get_action_details,
                                              list_actions, validate)

_TOOLS = [list_actions, get_action_details, describe_scenario, validate]


def create_server() -> FastMCP:
    mcp = FastMCP("scenario_execution")
    for fn in _TOOLS:
        mcp.tool()(fn)
    return mcp


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
