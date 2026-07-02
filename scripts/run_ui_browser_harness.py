from __future__ import annotations

from pathlib import Path
import os
import shutil
import socket
import subprocess
import sys
import time
from urllib import request
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "output" / "playwright"
SERVER_OUT = ROOT / "output" / "ui-harness"


def main() -> int:
    node = _find_node()
    if node is None:
        print("Node.js was not found. Install Node.js/npm or set PIP_PLANNER_NODE to a node executable.", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["NODE_PATH"] = _node_path(env.get("NODE_PATH"))
    browser = _find_browser_executable()
    if browser is not None:
        env.setdefault("PIP_PLANNER_BROWSER_EXECUTABLE", str(browser))

    port = _free_port()
    SERVER_OUT.mkdir(parents=True, exist_ok=True)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "pip_planner.web",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--out",
            str(SERVER_OUT),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    try:
        base_url = f"http://127.0.0.1:{port}/"
        _wait_for_url(base_url)
        completed = subprocess.run(
            [
                str(node),
                str(ROOT / "tests" / "ui_browser_harness.js"),
                base_url,
                str(ARTIFACT_DIR),
            ],
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=60,
        )
        if completed.stdout:
            print(completed.stdout)
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        if completed.returncode != 0:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            _print_server_output(server)
            return completed.returncode

        print(f"UI browser harness passed: {ARTIFACT_DIR / 'pip-planner-ui.png'}")
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


def _find_node() -> Path | None:
    explicit = os.environ.get("PIP_PLANNER_NODE")
    if explicit:
        path = Path(explicit)
        if path.exists():
            return path

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


def _node_path(existing: str | None) -> str:
    entries = []
    if existing:
        entries.append(existing)

    node_modules = (
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "node_modules"
    )
    if node_modules.exists():
        entries.append(str(node_modules))
        pnpm_root = node_modules / ".pnpm"
        if pnpm_root.exists():
            for path in pnpm_root.glob("playwright-core@*/node_modules"):
                entries.append(str(path))

    return os.pathsep.join(entries)


def _find_browser_executable() -> Path | None:
    explicit = os.environ.get("PIP_PLANNER_BROWSER_EXECUTABLE")
    if explicit and Path(explicit).exists():
        return Path(explicit)

    candidates: list[Path] = []
    if os.name == "nt":
        candidates.extend(
            [
                Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
                Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
                Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
                Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            ]
        )
    else:
        for name in ("google-chrome", "chromium", "chromium-browser", "msedge"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_url(url: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except URLError as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _print_server_output(server: subprocess.Popen[str]) -> None:
    if server.stdout is None:
        return
    try:
        output = server.stdout.read()
    except Exception:
        output = ""
    if output:
        print("Server output:", file=sys.stderr)
        print(output, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
