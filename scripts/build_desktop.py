from __future__ import annotations

from pathlib import Path
import tempfile
import os
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
TEMP_RELEASE_DIR = Path(tempfile.gettempdir()) / "pip-planner-electron-release"


def main() -> int:
    backend_exe = ROOT / "dist" / "backend" / "pip-planner-web" / "pip-planner-web.exe"
    if not backend_exe.exists():
        print(
            "Backend executable is missing. Run `python scripts/build_backend.py` first.",
            file=sys.stderr,
        )
        return 2

    node = _find_node()
    if node is None:
        print("Node.js was not found. Install Node.js/npm or set PIP_PLANNER_NODE.", file=sys.stderr)
        return 2

    builder = ROOT / "node_modules" / "electron-builder" / "out" / "cli" / "cli.js"
    if not builder.exists():
        print("electron-builder is missing. Run `pnpm install` first.", file=sys.stderr)
        return 2

    _remove_within_root(TEMP_RELEASE_DIR, Path(tempfile.gettempdir()))

    command = [
        str(node),
        str(builder),
        "--win",
        "portable",
        "--x64",
        "--publish",
        "never",
        "--config",
        str(ROOT / "electron-builder.yml"),
        f"-c.directories.output={TEMP_RELEASE_DIR}",
    ]
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode != 0:
        return completed.returncode

    _copy_release_artifacts()
    print(f"Copied packaged artifacts to {ROOT / 'release'}")
    return 0


def _copy_release_artifacts() -> None:
    release_dir = ROOT / "release"
    release_dir.mkdir(parents=True, exist_ok=True)
    build_dir = release_dir / time.strftime("build-%Y%m%d-%H%M%S")
    build_dir.mkdir(parents=False, exist_ok=False)

    for artifact in TEMP_RELEASE_DIR.iterdir():
        destination = build_dir / artifact.name
        if artifact.is_dir():
            shutil.copytree(artifact, destination)
        else:
            shutil.copy2(artifact, destination)
    latest_file = release_dir / "LATEST.txt"
    latest_file.write_text(str(build_dir), encoding="utf-8")
    print(f"Latest build directory: {build_dir}")


def _remove_within_root(path: Path, root: Path) -> None:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    if not resolved.exists():
        return
    last_error: Exception | None = None
    for _ in range(12):
        try:
            if resolved.is_dir():
                shutil.rmtree(resolved)
            else:
                resolved.unlink()
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(1)
    if last_error:
        raise last_error


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
