from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    steps = [
        [sys.executable, str(ROOT / "scripts" / "build_backend.py")],
        [sys.executable, str(ROOT / "scripts" / "build_desktop.py")],
    ]

    for command in steps:
        completed = subprocess.run(command, cwd=ROOT)
        if completed.returncode != 0:
            return completed.returncode

    print("Windows executable build completed. See the release/ directory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
