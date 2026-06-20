#!/usr/bin/env python3
"""Keep the RektFree plugin version in lockstep across all three manifest locations.

THE THREE-LOCATION PROBLEM
--------------------------
The plugin's version string is duplicated in three places that must always agree:

  1. .claude-plugin/plugin.json        -> top-level  ["version"]
  2. .claude-plugin/marketplace.json   -> top-level  ["version"]
  3. .claude-plugin/marketplace.json   -> plugin entry ["plugins"][i]["version"]
       (the entry whose ["name"] == "rektfree-plugin")

When these are bumped by hand they drift. This tool reads/writes all three at
once so they stay in sync.

USAGE
-----
  python3 scripts/version_sync.py            # --check (default): verify in-sync
  python3 scripts/version_sync.py --check    # explicit check
  python3 scripts/version_sync.py --set X.Y.Z  # write X.Y.Z to all three

--check  : prints the version and exits 0 if all three match; otherwise prints
           each location with its value and exits 1.
--set    : validates X.Y.Z as semver (\\d+\\.\\d+\\.\\d+), writes it everywhere,
           and prints what changed. Writes are done via a targeted regex on the
           "version": "..." fields so the rest of each file's formatting
           (inline arrays, spacing, key order) is preserved byte-for-byte. A
           no-op --set X.Y.Z (current value) leaves the files byte-identical.

Pure stdlib (json, argparse, re, pathlib, sys). No third-party imports.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# scripts/ lives at the repo root, so repo root = this file's parent's parent.
REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_JSON = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE_JSON = REPO_ROOT / ".claude-plugin" / "marketplace.json"

PLUGIN_ENTRY_NAME = "rektfree-plugin"
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _load(path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# Matches a   "version": "X.Y.Z"   field, capturing the surrounding quote/colon
# whitespace so it is reproduced exactly on replacement.
_VERSION_FIELD_RE = re.compile(r'("version"\s*:\s*")(\d+\.\d+\.\d+)(")')


def _replace_versions(path, new_version):
    """Rewrite every "version": "X.Y.Z" field in `path`, preserving all other
    formatting. Returns the number of fields replaced."""
    text = path.read_text(encoding="utf-8")
    new_text, count = _VERSION_FIELD_RE.subn(
        lambda m: f"{m.group(1)}{new_version}{m.group(3)}", text
    )
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return count


def _marketplace_entry_index(marketplace):
    plugins = marketplace.get("plugins", [])
    for i, entry in enumerate(plugins):
        if entry.get("name") == PLUGIN_ENTRY_NAME:
            return i
    raise SystemExit(
        f"error: no plugin entry named {PLUGIN_ENTRY_NAME!r} in {MARKETPLACE_JSON}"
    )


def read_versions():
    """Return a list of (label, value) for the three version locations."""
    plugin = _load(PLUGIN_JSON)
    marketplace = _load(MARKETPLACE_JSON)
    idx = _marketplace_entry_index(marketplace)
    return [
        ("plugin.json [version]", plugin.get("version")),
        ("marketplace.json [version]", marketplace.get("version")),
        (
            f'marketplace.json [plugins][{idx}][version] ({PLUGIN_ENTRY_NAME})',
            marketplace["plugins"][idx].get("version"),
        ),
    ]


def cmd_check():
    locations = read_versions()
    values = {v for _, v in locations}
    if len(values) == 1:
        version = next(iter(values))
        print(version)
        return 0
    print("Version mismatch across locations:")
    for label, value in locations:
        print(f"  {label}: {value}")
    return 1


def cmd_set(new_version):
    if not SEMVER_RE.match(new_version):
        print(
            f"error: {new_version!r} is not valid semver (expected \\d+.\\d+.\\d+)",
            file=sys.stderr,
        )
        return 2

    plugin = _load(PLUGIN_JSON)
    marketplace = _load(MARKETPLACE_JSON)
    idx = _marketplace_entry_index(marketplace)

    changes = []

    def maybe(label, old):
        if old != new_version:
            changes.append(f"  {label}: {old} -> {new_version}")
        else:
            changes.append(f"  {label}: {old} (unchanged)")

    maybe("plugin.json [version]", plugin.get("version"))
    maybe("marketplace.json [version]", marketplace.get("version"))
    maybe(
        f"marketplace.json [plugins][{idx}][version]",
        marketplace["plugins"][idx].get("version"),
    )

    # Write via targeted regex so existing formatting is preserved exactly.
    _replace_versions(PLUGIN_JSON, new_version)
    _replace_versions(MARKETPLACE_JSON, new_version)

    # Re-validate that both files are still well-formed JSON with the new value
    # everywhere (guards against a malformed manifest tripping up the regex).
    plugin_after = _load(PLUGIN_JSON)
    marketplace_after = _load(MARKETPLACE_JSON)
    idx_after = _marketplace_entry_index(marketplace_after)
    written = {
        plugin_after.get("version"),
        marketplace_after.get("version"),
        marketplace_after["plugins"][idx_after].get("version"),
    }
    if written != {new_version}:
        print(
            f"error: post-write verification failed; locations now hold {written}",
            file=sys.stderr,
        )
        return 1

    print(f"Set version to {new_version} in all three locations:")
    for line in changes:
        print(line)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Check or set the RektFree plugin version across all three manifests."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--check",
        action="store_true",
        help="Verify all three version locations match (default).",
    )
    group.add_argument(
        "--set",
        metavar="X.Y.Z",
        dest="set_version",
        help="Write semver X.Y.Z to all three version locations.",
    )
    args = parser.parse_args(argv)

    if args.set_version:
        return cmd_set(args.set_version)
    return cmd_check()


if __name__ == "__main__":
    sys.exit(main())
