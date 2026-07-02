from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "cli-harness"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [
        ["GTAC", "--architecture", "hairpin"],
        ["ATGC", "--architecture", "linear", "--at-mode", "py-py", "--tail", "none"],
    ]

    for case in cases:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_planner",
                "design",
                *case,
                "--out",
                str(OUT),
                "--format",
                "json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
        )
        if completed.returncode != 0:
            print(completed.stderr or completed.stdout, file=sys.stderr)
            return completed.returncode

        payload = json.loads(completed.stdout)
        for label in ("chemical_svg", "schematic_svg", "json"):
            path = Path(payload["files"][label])
            if not path.exists():
                print(f"Missing {label}: {path}", file=sys.stderr)
                return 1
        print(f"{payload['sequence_label']} -> {payload['chain_code']}")
        print(f"  chemical:  {payload['files']['chemical_svg']}")
        print(f"  schematic: {payload['files']['schematic_svg']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
