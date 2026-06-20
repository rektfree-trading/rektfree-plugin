#!/usr/bin/env python3
"""
RektFree MCP server — exposes the pure analysis engines as MCP tools.

This is the "brain-free" data layer of the plugin: it fetches market data and
runs the vendored analyzers, returning structured JSON. Claude itself (the host)
is the AI brain that interprets the numbers — so there are no AI-provider keys
here, by design.

Tools live one-per-module under ``tools/``; each exposes a ``register(mcp)``
function. This file auto-discovers and registers every such module, so adding a
new tool is just dropping a new ``tools/<name>.py`` — no edits here.

Run as a stdio MCP server:  python3 server.py
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import sys

# Allow `from engines import ...` / `from data import ...` / `from tools import
# ...` when launched by absolute path (the plugin sets cwd elsewhere). Add our
# own dir to sys.path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import tools  # noqa: E402

mcp = FastMCP("rektfree")


def _register_all_tools() -> list[str]:
    """Import every module in ``tools/`` and call its ``register(mcp)``.

    Modules whose name starts with ``_`` (e.g. ``_common``) are skipped — they
    are shared helpers, not tool modules. Returns the list of registered module
    names for logging/diagnostics.
    """
    registered: list[str] = []
    for _finder, modname, _ispkg in pkgutil.iter_modules(tools.__path__):
        if modname.startswith("_"):
            continue
        module = importlib.import_module(f"tools.{modname}")
        register = getattr(module, "register", None)
        if callable(register):
            register(mcp)
            registered.append(modname)
    return registered


_register_all_tools()


if __name__ == "__main__":
    mcp.run()
