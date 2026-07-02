from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    csc = _find_csc()
    if csc is None:
        print("C# compiler was not found. Cannot build the dev launcher.", file=sys.stderr)
        return 2

    source = ROOT / "launcher" / "PipPlannerDevLauncher.cs"
    output = ROOT / "PIP Planner Dev.exe"
    command = [
        str(csc),
        "/nologo",
        "/target:winexe",
        "/optimize+",
        "/platform:x64",
        f"/out:{output}",
        f"/win32icon:{ROOT / 'assets' / 'icons' / 'icon.ico'}",
        "/reference:System.dll",
        "/reference:System.Windows.Forms.dll",
        str(source),
    ]
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        return completed.returncode

    print(f"Built development launcher: {output}")
    return 0


def _find_csc() -> Path | None:
    explicit = os.environ.get("PIP_PLANNER_CSC")
    if explicit and Path(explicit).exists():
        return Path(explicit)

    candidates = [
        Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    found = shutil.which("csc")
    if found:
        return Path(found)

    return None


if __name__ == "__main__":
    raise SystemExit(main())
