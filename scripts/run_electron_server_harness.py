from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    node = _find_node()
    if node is None:
        print("Node.js was not found. Install Node.js/npm or set PIP_PLANNER_NODE.", file=sys.stderr)
        return 2

    completed = subprocess.run(
        [str(node), str(ROOT / "tests" / "electron_server_harness.js")],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def _find_node() -> Path | None:
    explicit = os.environ.get("PIP_PLANNER_NODE")
    if explicit and Path(explicit).exists():
        return Path(explicit)

    on_path = shutil.which("node")
    if on_path:
        return Path(on_path)

    executable = "node.exe" if os.name == "nt" else "node"
    bundled = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / executable
    )
    if bundled.exists():
        return bundled
    return None


if __name__ == "__main__":
    raise SystemExit(main())
