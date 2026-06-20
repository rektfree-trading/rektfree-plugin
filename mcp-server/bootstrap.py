#!/usr/bin/env python3
"""
RektFree MCP server bootstrap launcher.

Why this exists
---------------
The MCP server (``server.py``) imports third-party packages (``mcp``, ``httpx``)
at module load. On a fresh machine the user's bare ``python3`` almost never has
those installed, so launching ``server.py`` directly crashes on import and
Claude Code shows the server as "not connected". Previously the fix was a manual
``pip install -r requirements.txt`` + a manual ``/mcp`` reconnect — exactly the
onboarding friction we want gone.

This launcher makes the server self-bootstrap its dependencies so it works right
after ``/plugin install`` with no manual steps:

  * Fast path — if a usable interpreter (our cached venv, or the current
    ``python3``) already has ``mcp`` + ``httpx``, we ``os.execv`` straight into
    ``server.py`` with zero install latency.
  * First run — we create a venv with the stdlib ``venv`` module, ``pip
    install`` the pinned requirements into it, then exec ``server.py``.

Venv location
-------------
We use a per-user CACHE dir (``~/.cache/rektfree-plugin/venv`` on Linux,
``~/Library/Caches/rektfree-plugin/venv`` on macOS, ``%LOCALAPPDATA%`` on
Windows) rather than ``${CLAUDE_PLUGIN_ROOT}/.venv`` because:
  * the plugin dir may be read-only or wiped/replaced on reinstall, while the
    cache survives — so a reinstall reuses the already-built venv (fast path);
  * it keeps the plugin tree clean.

stdio discipline
----------------
stdout is the MCP transport. We never write to stdout before exec. All progress
notes go to stderr. We exec (never wrap in a buffered subprocess) so the stdio
pipes are inherited cleanly by ``server.py``.

Idempotency / timeout
---------------------
First-run venv + pip can take ~10-30s and may exceed Claude Code's connect
timeout, so the FIRST connect can still fail — but the venv finishes building
and the NEXT connect (or a manual ``/mcp`` reconnect) hits the fast path and
succeeds immediately. A file lock prevents two concurrent reconnects from
racing on the same venv.

stdlib only — this file CANNOT import mcp/httpx (they may not exist yet).
Python 3.10+.
"""

from __future__ import annotations

import os
import subprocess
import sys
import venv as _venv
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent
SERVER = HERE / "server.py"
REQUIREMENTS = HERE / "requirements.txt"

# Packages the server needs at import time; used for the fast-path check.
_REQUIRED_MODULES = ("mcp", "httpx")


def _log(msg: str) -> None:
    """Write a one-line note to stderr (never stdout — that is the transport)."""
    sys.stderr.write(f"[rektfree-bootstrap] {msg}\n")
    sys.stderr.flush()


def _cache_root() -> Path:
    """Per-OS, per-user writable cache dir for the bootstrap venv."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:  # linux / other posix
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "rektfree-plugin"


def _venv_dir() -> Path:
    return _cache_root() / "venv"


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _has_deps(python: Path) -> bool:
    """Return True if ``python`` can import every required module."""
    if not python.exists():
        return False
    check = "import " + ", ".join(_REQUIRED_MODULES)
    try:
        proc = subprocess.run(
            [str(python), "-c", check],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _exec_server(python: Path) -> None:
    """Replace this process with the server. Never returns on success."""
    env = dict(os.environ)
    # server.py also self-adds its dir, but set PYTHONPATH for belt-and-braces.
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(HERE) + (os.pathsep + existing if existing else "")
    _log(f"launching server with {python}")
    os.execve(str(python), [str(python), str(SERVER)], env)


def _build_venv(venv_dir: Path) -> Path:
    """Create the venv (if needed) and install pinned deps. Returns its python.

    A lock file serialises concurrent reconnects so two processes don't pip
    into the same venv simultaneously. We re-check the fast path after acquiring
    the lock so a reconnect that arrives just after the first run finished does
    no extra work.
    """
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    lock = venv_dir.parent / "venv.lock"

    fd = _acquire_lock(lock)
    try:
        python = _venv_python(venv_dir)
        # Someone may have finished building while we waited for the lock.
        if _has_deps(python):
            _log("venv ready (built by a concurrent run)")
            return python

        _log(
            "first run: setting up an isolated Python environment (mcp, httpx). "
            "This one-time setup takes ~10-30s; if Claude Code reports the "
            "server failed to connect, just reconnect via /mcp once setup "
            "finishes — it will connect instantly."
        )

        if not python.exists():
            _log(f"creating venv at {venv_dir}")
            builder = _venv.EnvBuilder(with_pip=True, clear=False, upgrade=False)
            builder.create(str(venv_dir))

        _log("installing pinned requirements (quiet)...")
        proc = subprocess.run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-input",
                "--disable-pip-version-check",
                "-q",
                "-r",
                str(REQUIREMENTS),
            ],
            stdout=sys.stderr.fileno(),  # keep stdout clean; pip noise -> stderr
            stderr=sys.stderr.fileno(),
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pip install failed (exit {proc.returncode})")

        if not _has_deps(python):
            raise RuntimeError("deps still missing after install")

        _log("setup complete — environment is ready")
        return python
    finally:
        _release_lock(fd, lock)


# --- simple cross-platform advisory file lock ------------------------------

def _acquire_lock(lock: Path):
    """Best-effort exclusive lock. Returns a file descriptor to release."""
    fd = os.open(str(lock), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError:
        # If locking is unavailable, proceed unlocked — worst case is a
        # redundant pip install, which is still idempotent/correct.
        pass
    return fd


def _release_lock(fd, lock: Path) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    venv_dir = _venv_dir()
    venv_py = _venv_python(venv_dir)

    # 1) Fast path: cached venv already has deps -> exec immediately.
    if _has_deps(venv_py):
        _exec_server(venv_py)
        return  # unreachable on success

    # 2) Fast path on the current interpreter: if whatever launched us already
    #    has mcp+httpx (e.g. user pre-installed, or dev machine), just use it —
    #    no venv build, no latency.
    current = Path(sys.executable)
    if _has_deps(current):
        _log("current interpreter already has deps — skipping venv build")
        _exec_server(current)
        return

    # 3) First run: build the venv, install deps, then exec.
    try:
        python = _build_venv(venv_dir)
    except Exception as exc:  # noqa: BLE001 — surface any failure clearly
        _log(f"ERROR: dependency setup failed: {exc}")
        # Last-ditch graceful fallback: maybe the current interpreter sprouted
        # the deps meanwhile, or a partial build is usable.
        if _has_deps(current):
            _log("falling back to current interpreter")
            _exec_server(current)
            return
        if _has_deps(venv_py):
            _exec_server(venv_py)
            return
        _log(
            "Could not prepare dependencies. Manually run: "
            f"python3 -m pip install -r {REQUIREMENTS}  then reconnect via /mcp."
        )
        sys.exit(1)

    _exec_server(python)


if __name__ == "__main__":
    main()
