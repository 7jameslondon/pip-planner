from __future__ import annotations

from pathlib import Path
import importlib.util
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist" / "backend"
WORK_DIR = ROOT / "build" / "pyinstaller"
SPEC_DIR = ROOT / "build" / "pyinstaller-spec"
ENTRYPOINT = ROOT / "pip_planner" / "web_entry.py"


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is required. Install it with: python -m pip install pyinstaller", file=sys.stderr)
        return 2

    for path in (DIST_DIR / "pip-planner-web", WORK_DIR, SPEC_DIR):
        _remove_within_workspace(path)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--contents-directory",
        ".",
        "--name",
        "pip-planner-web",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(WORK_DIR),
        "--specpath",
        str(SPEC_DIR),
        "--collect-all",
        "rdkit",
        "--collect-all",
        "numpy",
        "--collect-all",
        "PIL",
        *_optional_package_args(),
        "--hidden-import",
        "pip_planner.web",
        "--noupx",
        str(ENTRYPOINT),
    ]

    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        return completed.returncode

    executable = DIST_DIR / "pip-planner-web" / "pip-planner-web.exe"
    if not executable.exists():
        print(f"Expected backend executable was not created: {executable}", file=sys.stderr)
        return 1

    print(f"Built backend executable: {executable}")
    return 0


def _optional_package_args() -> list[str]:
    args: list[str] = []
    for package_name in ("admet_ai", "soltrannet"):
        if importlib.util.find_spec(package_name) is None:
            continue
        print(f"Including optional solubility package in backend build: {package_name}")
        args.extend(["--collect-all", package_name])
    return args


def _remove_within_workspace(path: Path) -> None:
    resolved = path.resolve()
    resolved.relative_to(ROOT.resolve())
    if resolved.exists():
        shutil.rmtree(resolved)


if __name__ == "__main__":
    raise SystemExit(main())
