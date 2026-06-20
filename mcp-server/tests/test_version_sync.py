"""Offline guardrail: assert the plugin version is in sync across all three manifests.

The plugin version is duplicated in three places that must agree:

  1. .claude-plugin/plugin.json        -> ["version"]
  2. .claude-plugin/marketplace.json   -> ["version"]
  3. .claude-plugin/marketplace.json   -> ["plugins"][i]["version"]  (rektfree-plugin)

This test fails (catching drift before release) if they disagree. It does NOT
hardcode the version value, so it stays valid across future bumps.

Dependency-free: stdlib + pytest only.
"""

import json
from pathlib import Path

# This file lives at <repo>/mcp-server/tests/, so repo root = three parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / ".claude-plugin"
PLUGIN_JSON = PLUGIN_DIR / "plugin.json"
MARKETPLACE_JSON = PLUGIN_DIR / "marketplace.json"

PLUGIN_ENTRY_NAME = "rektfree-plugin"


def _load(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_repo_root_resolves():
    assert PLUGIN_DIR.is_dir(), (
        f"expected .claude-plugin/ at repo root, got {PLUGIN_DIR} "
        "(repo-root path resolution is wrong)"
    )


def test_versions_in_sync():
    plugin = _load(PLUGIN_JSON)
    marketplace = _load(MARKETPLACE_JSON)

    entry = next(
        (p for p in marketplace.get("plugins", []) if p.get("name") == PLUGIN_ENTRY_NAME),
        None,
    )
    assert entry is not None, (
        f"no plugin entry named {PLUGIN_ENTRY_NAME!r} in {MARKETPLACE_JSON}"
    )

    plugin_version = plugin.get("version")
    marketplace_version = marketplace.get("version")
    entry_version = entry.get("version")

    assert plugin_version == marketplace_version == entry_version, (
        "plugin version drift detected: "
        f"plugin.json[version]={plugin_version!r}, "
        f"marketplace.json[version]={marketplace_version!r}, "
        f"marketplace.json[plugins][{PLUGIN_ENTRY_NAME}][version]={entry_version!r}"
    )
