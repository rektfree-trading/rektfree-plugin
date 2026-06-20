"""
Tool modules for the RektFree MCP server.

Each module in this package exposes a ``register(mcp)`` function that attaches
one or more ``@mcp.tool()`` callables to the shared FastMCP instance. ``server.py``
auto-discovers and registers every module here at startup, so adding a new tool
means dropping a new ``tools/<name>.py`` file — no edits to ``server.py`` needed.
"""
