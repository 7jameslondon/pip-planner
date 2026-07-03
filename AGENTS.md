# AGENTS

This project is a small, dependency-light Python application. Keep the CLI as the source of truth and have every UI/server path call the CLI instead of duplicating design logic.

## Commands

- Unit/API tests: `python -m unittest discover`
- CLI harness: `python scripts/run_cli_harness.py`
- Real browser UI harness: `python scripts/run_ui_browser_harness.py`
- Electron server harness: `pnpm test:electron-server`
- Electron native smoke harness: `pnpm test:electron-smoke`
- Packaged executable smoke harness: `pnpm test:packaged`
- Build Windows executable: `pnpm build`
- Start UI: `python -m pip_planner.web --host 127.0.0.1 --port 8765`
- Start native desktop UI: `pnpm desktop`

## Implementation Notes

- Core mapping and validation live in `pip_planner/model.py`.
- RDKit molecular graph construction lives in `pip_planner/chemistry.py`.
- SVG renderers live in `pip_planner/svg.py`.
- CLI behavior lives in `pip_planner/cli.py`.
- The local web UI lives in `pip_planner/web.py` and must call `python -m pip_planner design`.
- The Electron desktop wrapper lives in `electron/` and must start `pip_planner.web` rather than reimplementing UI or design logic.
- Build scripts live in `scripts/build_*.py`.
- Generated artifacts belong under `output/`, `build/`, `dist/`, and `release/`, which are intentionally gitignored.

## Quality Bar

- Update tests when changing mapping, file output, CLI options, or UI API behavior.
- Run `python -m unittest discover` before handoff.
- Run `python scripts/run_ui_browser_harness.py` after UI or SVG layout changes.
- Run `pnpm test:electron-server` after changing `electron/` process startup code.
- Run `pnpm test:electron-smoke` after changing Electron window startup behavior.
- `pnpm build` can take more than 10 minutes; only run it when explicitly requested. Run `pnpm test:packaged` after changing packaging, backend startup, or Electron build config.
- RDKit is the required chemistry backend for chemical SVG output. Do not reintroduce hand-drawn chemical structures as the primary renderer.
- Treat the chemical SVG as a planning visualization until terminal caps/linkers are confirmed for synthesis.
