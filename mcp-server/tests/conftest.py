"""
Pytest config for the RektFree plugin's MCP server.

Adds the ``mcp-server`` dir to ``sys.path`` so tests can ``from engines import
…`` / ``from data import …`` / ``from tools import …`` exactly like ``server.py``
does at runtime. Live tests (those that hit the public Binance API) are marked
``@pytest.mark.live`` and skipped unless ``RF_LIVE_TESTS=1`` is set, so the
default suite is fully offline and deterministic.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live: test hits the live Binance API — set RF_LIVE_TESTS=1 to run.",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RF_LIVE_TESTS"):
        return
    skip_live = pytest.mark.skip(reason="live test; set RF_LIVE_TESTS=1 to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
