from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SPLASH_TARGET_MS = 500.0
EVENT_NAME = "splash-did-finish-load"


@dataclass(frozen=True)
class Target:
    name: str
    command: list[str]
    event_name: str = EVENT_NAME
    required: bool = True
    enforce_splash_target: bool = True
    extra_env: dict[str, str] | None = None


def main() -> int:
    targets = _targets()
    failures = []

    for target in targets:
        result = _measure_target(target)
        if result is None:
            if target.required:
                failures.append(f"{target.name}: target was not available")
            continue

        event_ms = result["event_ms"]
        observed_ms = result["observed_ms"]
        print(
            f"{target.name}: {target.event_name}={event_ms:.1f} ms "
            f"(observed {observed_ms:.1f} ms from launch)"
        )
        if target.enforce_splash_target and observed_ms > SPLASH_TARGET_MS:
            failures.append(
                f"{target.name}: splash observed at {observed_ms:.1f} ms, "
                f"over {SPLASH_TARGET_MS:.0f} ms target"
            )
        elif not target.enforce_splash_target:
            print(f"{target.name}: timing is informational; only launcher-exe is held to the packaged splash target")

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1

    return 0


def _targets() -> list[Target]:
    electron = ROOT / "node_modules" / "electron" / "dist" / "electron.exe"
    targets: list[Target] = []
    if electron.exists():
        targets.append(
            Target(
                "dev-electron",
                [str(electron), "."],
                required=False,
                enforce_splash_target=False,
            )
        )

    latest = _latest_release_dir()
    if latest is not None:
        portable_launcher = latest / "PIP Planner.exe"
        unpacked = latest / "win-unpacked" / "PIP Planner.exe"
        if portable_launcher.exists():
            targets.append(
                Target(
                    "single-file-portable-exe",
                    [str(portable_launcher)],
                    event_name="launcher-splash-shown",
                    extra_env={"PIP_PLANNER_LAUNCHER_SMOKE": "1"},
                )
            )
        if unpacked.exists():
            targets.append(
                Target(
                    "unpacked-exe",
                    _packaged_command(unpacked),
                    enforce_splash_target=False,
                )
            )

    return targets


def _measure_target(target: Target) -> dict[str, float] | None:
    timing_file = Path(tempfile.gettempdir()) / f"pip-planner-startup-{os.getpid()}-{time.time_ns()}.jsonl"
    env = os.environ.copy()
    env["PIP_PLANNER_ELECTRON_SMOKE"] = "1"
    env["PIP_PLANNER_STARTUP_TIMING_FILE"] = str(timing_file)
    if target.extra_env:
        env.update(target.extra_env)

    started = time.perf_counter()
    try:
        process = subprocess.Popen(
            target.command,
            cwd=ROOT,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        return None

    event_ms: float | None = None
    observed_ms: float | None = None
    deadline = time.perf_counter() + 120
    process_exited_at: float | None = None
    while time.perf_counter() < deadline:
        event_ms = _read_event_ms(timing_file, target.event_name)
        if event_ms is not None:
            observed_ms = (time.perf_counter() - started) * 1000
            break
        if process.poll() is not None and process_exited_at is None:
            process_exited_at = time.perf_counter()
        if process_exited_at is not None and time.perf_counter() - process_exited_at > 5:
            break
        time.sleep(0.01)

    try:
        stdout, stderr = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate(timeout=10)

    if timing_file.exists():
        timing_file.unlink()

    if process.returncode not in (0, None):
        _print_process_output(target.name, stdout, stderr)
        raise RuntimeError(f"{target.name} exited with code {process.returncode}")

    if event_ms is None or observed_ms is None:
        _print_process_output(target.name, stdout, stderr)
        raise RuntimeError(f"{target.name} did not report {target.event_name}")

    return {"event_ms": event_ms, "observed_ms": observed_ms}


def _read_event_ms(path: Path, event_name: str) -> float | None:
    if not path.exists():
        return None

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event") == event_name:
            return float(event["elapsed_ms"])
    return None


def _print_process_output(name: str, stdout: str, stderr: str) -> None:
    if stdout:
        print(f"{name} stdout:\n{stdout}", file=sys.stderr)
    if stderr:
        print(f"{name} stderr:\n{stderr}", file=sys.stderr)


def _packaged_command(executable: Path) -> list[str]:
    return [
        str(executable),
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-gpu-sandbox",
        "--disable-software-rasterizer",
        "--in-process-gpu",
        "--no-sandbox",
    ]


def _latest_release_dir() -> Path | None:
    latest = ROOT / "release" / "LATEST.txt"
    if latest.exists():
        candidate = Path(latest.read_text(encoding="utf-8").strip())
        if candidate.exists():
            return candidate

    release = ROOT / "release"
    if not release.exists():
        return None

    matches = sorted(release.glob("build-*"), reverse=True)
    return matches[0] if matches else None


if __name__ == "__main__":
    raise SystemExit(main())
