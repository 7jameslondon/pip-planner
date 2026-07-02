from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    electron = ROOT / "node_modules" / "electron" / "dist" / "electron.exe"
    if not electron.exists():
        print(
            "Electron runtime was not found. Run `pnpm install`, then retry.",
            file=sys.stderr,
        )
        return 2

    env = os.environ.copy()
    env["PIP_PLANNER_ELECTRON_SMOKE"] = "1"
    completed = subprocess.run(
        [str(electron), "."],
        cwd=ROOT,
        env=env,
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
    if completed.returncode != 0:
        return completed.returncode
    if "electron-smoke-loaded=true" not in completed.stdout:
        print("Electron smoke output did not confirm the UI loaded.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
