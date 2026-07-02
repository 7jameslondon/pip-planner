from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    executable = _find_packaged_executable()
    if executable is None:
        print("Packaged executable was not found. Run `pnpm build` first.", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["PIP_PLANNER_ELECTRON_SMOKE"] = "1"
    smoke_root = Path(tempfile.mkdtemp(prefix="pip-planner-packaged-smoke-"))
    try:
        isolated_executable = smoke_root / executable.name
        shutil.copy2(executable, isolated_executable)
        env["PIP_PLANNER_PORTABLE_CACHE_ROOT"] = str(smoke_root / "cache")

        completed = subprocess.run(
            [
                str(isolated_executable),
                "--disable-gpu",
                "--disable-gpu-compositing",
                "--disable-gpu-sandbox",
                "--disable-software-rasterizer",
                "--in-process-gpu",
                "--no-sandbox",
            ],
            cwd=smoke_root,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=180,
        )
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode != 0:
            return completed.returncode
        if "electron-splash-created=true" not in completed.stdout:
            print("Packaged smoke output did not confirm the splash window was created.", file=sys.stderr)
            return 1
        if "electron-smoke-loaded=true" not in completed.stdout:
            print("Packaged smoke output did not confirm the UI loaded.", file=sys.stderr)
            return 1
        print(f"Packaged smoke passed with isolated single-file exe: {executable}")
        return 0
    finally:
        shutil.rmtree(smoke_root, ignore_errors=True)


def _find_packaged_executable() -> Path | None:
    candidates = []
    release_dir = ROOT / "release"
    if release_dir.exists():
        build_dirs = sorted(release_dir.glob("build-*"), reverse=True)
        for build_dir in build_dirs:
            candidates.extend(
                [
                    build_dir / "PIP Planner.exe",
                    build_dir / "win-unpacked" / "PIP Planner.exe",
                ]
            )

    candidates.extend(
        [
            ROOT / "release" / "PIP Planner.exe",
            ROOT / "release" / "win-unpacked" / "PIP Planner.exe",
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate

    release_dir = ROOT / "release"
    if release_dir.exists():
        matches = sorted(release_dir.glob("PIP Planner*.exe"))
        if matches:
            return matches[0]
    return None


if __name__ == "__main__":
    raise SystemExit(main())
