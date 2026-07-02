from __future__ import annotations

from pathlib import Path
import hashlib
import tempfile
import os
import shutil
import subprocess
import struct
import sys
import time
import zipfile


ROOT = Path(__file__).resolve().parents[1]
TEMP_RELEASE_DIR = Path(tempfile.gettempdir()) / "pip-planner-electron-release"
PAYLOAD_MAGIC = b"PIPPLANNERPKGv1"


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

    build_dir = _copy_release_artifacts()
    _remove_electron_portable(build_dir)
    completed = _build_launcher(build_dir)
    if completed.returncode != 0:
        return completed.returncode
    _append_payload(build_dir / "PIP Planner.exe", build_dir / "win-unpacked")
    _write_latest_build(build_dir)
    print(f"Copied packaged artifacts to {ROOT / 'release'}")
    return 0


def _copy_release_artifacts() -> Path:
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
    print(f"Latest build directory: {build_dir}")
    return build_dir


def _build_launcher(build_dir: Path) -> subprocess.CompletedProcess:
    csc = _find_csc()
    if csc is None:
        print("C# compiler was not found. Cannot build native splash launcher.", file=sys.stderr)
        return subprocess.CompletedProcess([], 2)

    launcher_source = ROOT / "launcher" / "PipPlannerLauncher.cs"
    launcher_exe = build_dir / "PIP Planner.exe"
    command = [
        str(csc),
        "/nologo",
        "/target:winexe",
        "/optimize+",
        "/platform:x64",
        f"/out:{launcher_exe}",
        f"/win32icon:{ROOT / 'assets' / 'icons' / 'icon.ico'}",
        "/reference:System.dll",
        "/reference:System.Drawing.dll",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll",
        "/reference:System.Windows.Forms.dll",
        str(launcher_source),
    ]
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode == 0:
        print(f"Built native splash launcher stub: {launcher_exe}")
    return completed


def _append_payload(launcher_exe: Path, unpacked_dir: Path) -> None:
    if not unpacked_dir.exists():
        raise FileNotFoundError(f"Cannot build single-file portable exe; missing {unpacked_dir}")

    payload_zip = Path(tempfile.gettempdir()) / f"pip-planner-payload-{os.getpid()}-{time.time_ns()}.zip"
    try:
        _create_payload_zip(unpacked_dir, payload_zip)
        digest = hashlib.sha256()
        payload_size = 0
        with payload_zip.open("rb") as source, launcher_exe.open("ab") as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                payload_size += len(chunk)
                target.write(chunk)
            target.write(struct.pack("<q", payload_size))
            target.write(digest.hexdigest().encode("ascii"))
            target.write(PAYLOAD_MAGIC)
        print(
            "Embedded portable payload: "
            f"{payload_size / (1024 * 1024):.1f} MiB, sha256={digest.hexdigest()[:16]}..."
        )
        print(f"Built single-file portable executable: {launcher_exe}")
    finally:
        if payload_zip.exists():
            payload_zip.unlink()


def _create_payload_zip(source_dir: Path, payload_zip: Path) -> None:
    with zipfile.ZipFile(payload_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir).as_posix())


def _remove_electron_portable(build_dir: Path) -> None:
    for artifact in build_dir.glob("PIP Planner-*-x64.exe"):
        artifact.unlink()


def _write_latest_build(build_dir: Path) -> None:
    release_dir = ROOT / "release"
    latest_file = release_dir / "LATEST.txt"
    latest_file.write_text(str(build_dir), encoding="utf-8")


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
