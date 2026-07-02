from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import unquote, urlparse
import uuid

from .model import safe_design_name


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>PIP Planner</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fa;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #667085;
      --line: #d0d7e2;
      --blue: #225c8f;
      --blue-soft: #eaf2fb;
      --green: #25715f;
      --amber: #7a5a16;
      --amber-soft: #fbf3dd;
      --danger: #9c2f2f;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
    }
    .app {
      display: grid;
      grid-template-columns: minmax(300px, 380px) minmax(0, 1fr);
      gap: 0;
      min-height: 100vh;
    }
    aside {
      background: var(--panel);
      border-right: 1px solid var(--line);
      padding: 24px;
    }
    main {
      padding: 24px;
      min-width: 0;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 24px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .subtle {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      margin: 0 0 22px;
    }
    label {
      display: block;
      font-size: 13px;
      font-weight: 700;
      margin: 18px 0 8px;
    }
    textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      font: inherit;
      min-height: 116px;
      padding: 12px;
    }
    select {
      min-height: 40px;
      padding: 8px 10px;
    }
    textarea:focus, select:focus, button:focus-visible, a:focus-visible {
      outline: 3px solid #9cc8ed;
      outline-offset: 2px;
    }
    .segmented {
      display: grid;
      grid-template-columns: 1fr 1fr;
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: #fff;
    }
    .segmented label {
      margin: 0;
      padding: 10px 12px;
      font-size: 14px;
      font-weight: 700;
      text-align: center;
      cursor: pointer;
      border-right: 1px solid var(--line);
    }
    .segmented label:last-child { border-right: 0; }
    .segmented input { position: absolute; opacity: 0; pointer-events: none; }
    .segmented label:has(input:checked) {
      color: #ffffff;
      background: var(--blue);
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .primary {
      width: 100%;
      margin-top: 20px;
      border: 0;
      border-radius: 8px;
      background: var(--green);
      color: #fff;
      min-height: 44px;
      font-weight: 700;
      cursor: pointer;
    }
    .primary:disabled {
      cursor: wait;
      opacity: 0.72;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 12px;
      min-width: 0;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
    }
    .metric strong {
      display: block;
      overflow-wrap: anywhere;
      font-family: Consolas, 'Liberation Mono', monospace;
      font-size: 14px;
      line-height: 1.35;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      margin: 0 0 12px;
    }
    .tab, .download {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      color: var(--ink);
      padding: 8px 12px;
      min-height: 36px;
      text-decoration: none;
      font: inherit;
      cursor: pointer;
    }
    .tab[aria-selected="true"] {
      background: var(--blue-soft);
      color: var(--blue);
      border-color: #9fc0ea;
      font-weight: 700;
    }
    .download {
      margin-left: auto;
      color: var(--blue);
      font-weight: 700;
    }
    .download.secondary {
      margin-left: 0;
    }
    .preview {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      min-height: 520px;
      overflow: auto;
      padding: 18px;
    }
    .preview svg {
      max-width: 100%;
      height: auto;
      display: block;
    }
    .message {
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 13px;
      line-height: 1.45;
      margin: 12px 0 0;
      display: none;
    }
    .message.is-visible { display: block; }
    .message.warn {
      background: var(--amber-soft);
      color: var(--amber);
      border: 1px solid #e7cd87;
    }
    .message.error {
      background: #fce8e8;
      color: var(--danger);
      border: 1px solid #efb3b3;
    }
    .files {
      margin-top: 14px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .empty {
      color: var(--muted);
      font-size: 14px;
      padding: 28px;
      text-align: center;
    }
    @media (max-width: 880px) {
      .app { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      main { padding: 18px; }
      .summary { grid-template-columns: 1fr 1fr; }
      .download { margin-left: 0; }
    }
    @media (max-width: 540px) {
      aside { padding: 18px; }
      .row, .summary { grid-template-columns: 1fr; }
      .toolbar { align-items: stretch; }
      .tab, .download { width: 100%; text-align: center; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside>
      <h1>PIP Planner</h1>
      <p class="subtle">Enter a 5' to 3' DNA target strand. The UI sends the request to the local CLI and displays the generated files.</p>

      <form id="design-form">
        <label for="sequence">DNA sequence</label>
        <textarea id="sequence" name="sequence" spellcheck="false" autocomplete="off">GTAC</textarea>

        <label>Architecture</label>
        <div class="segmented" role="radiogroup" aria-label="Polyamide architecture">
          <label><input type="radio" name="architecture" value="hairpin" checked>Hairpin</label>
          <label><input type="radio" name="architecture" value="linear">Linear</label>
        </div>

        <label for="at-mode">A/T recognition</label>
        <select id="at-mode" name="at_mode">
          <option value="distinguish">Distinguish A-T and T-A with Hp</option>
          <option value="py-py">Treat A/T as Py/Py</option>
        </select>

        <div class="row">
          <div>
            <label for="tail">Terminal group</label>
            <select id="tail" name="tail">
              <option value="dp">Dp</option>
              <option value="none">None</option>
            </select>
          </div>
          <div>
            <label for="turn">Hairpin turn</label>
            <select id="turn" name="turn">
              <option value="gamma">Gamma</option>
              <option value="beta">Beta</option>
              <option value="none">None</option>
            </select>
          </div>
        </div>

        <button class="primary" type="submit" id="submit">Update now</button>
      </form>

      <div class="message warn" id="warnings"></div>
      <div class="message error" id="errors"></div>
    </aside>

    <main>
      <section class="summary" aria-label="Design summary">
        <div class="metric"><span>Target</span><strong id="metric-target">-</strong></div>
        <div class="metric"><span>Complement</span><strong id="metric-complement">-</strong></div>
        <div class="metric"><span>Pairs</span><strong id="metric-pairs">-</strong></div>
        <div class="metric"><span>Chain</span><strong id="metric-chain">-</strong></div>
      </section>

      <div class="toolbar">
        <button class="tab" type="button" data-view="chemical" aria-selected="true">Chemical structure</button>
        <button class="tab" type="button" data-view="schematic" aria-selected="false">Schematic</button>
        <a class="download" id="download-chemical" href="#" download>Download chemical SVG</a>
        <a class="download secondary" id="download-schematic" href="#" download>Download schematic SVG</a>
      </div>

      <section class="preview" id="preview" aria-live="polite">
        <div class="empty">No design has been generated yet.</div>
      </section>
      <div class="files" id="files"></div>
    </main>
  </div>

  <script>
    const form = document.querySelector('#design-form');
    const submit = document.querySelector('#submit');
    const preview = document.querySelector('#preview');
    const warnings = document.querySelector('#warnings');
    const errors = document.querySelector('#errors');
    const tabs = [...document.querySelectorAll('.tab')];
    let currentResult = null;
    let currentView = 'chemical';
    let designTimer = null;
    let activeDesignRequest = 0;
    let lastQueuedPayload = '';

    function payloadFromForm() {
      const data = new FormData(form);
      return {
        sequence: data.get('sequence'),
        architecture: data.get('architecture'),
        at_mode: data.get('at_mode'),
        tail: data.get('tail'),
        turn: data.get('turn')
      };
    }

    function showMessage(element, text) {
      element.textContent = text || '';
      element.classList.toggle('is-visible', Boolean(text));
    }

    function renderResult(result) {
      currentResult = result;
      const design = result.design;
      document.querySelector('#metric-target').textContent = design.sequence_label;
      document.querySelector('#metric-complement').textContent = design.complement_label;
      document.querySelector('#metric-pairs').textContent = design.recognition_pairs.join(' ');
      document.querySelector('#metric-chain').textContent = design.chain_code;
      showMessage(warnings, design.warnings.join(' '));
      showMessage(errors, '');

      document.querySelector('#download-chemical').href = result.generated.chemical_svg_url;
      document.querySelector('#download-schematic').href = result.generated.schematic_svg_url;
      document.querySelector('#download-chemical').download = result.generated.chemical_svg_name;
      document.querySelector('#download-schematic').download = result.generated.schematic_svg_name;
      document.querySelector('#files').textContent =
        'Generated with ' + design.chemical_renderer + '. SMILES: ' + design.chemical_smiles +
        ' | Files: ' + design.files.chemical_svg + ' | ' + design.files.schematic_svg;

      renderPreview();
    }

    function renderPreview() {
      if (!currentResult) return;
      preview.innerHTML = currentView === 'chemical'
        ? currentResult.chemical_svg
        : currentResult.schematic_svg;
      tabs.forEach(tab => {
        tab.setAttribute('aria-selected', String(tab.dataset.view === currentView));
      });
    }

    function scheduleDesign(delay = 250) {
      const payloadKey = JSON.stringify(payloadFromForm());
      if (payloadKey === lastQueuedPayload) return;
      lastQueuedPayload = payloadKey;
      const requestId = activeDesignRequest + 1;
      activeDesignRequest = requestId;
      window.clearTimeout(designTimer);
      designTimer = window.setTimeout(() => design(null, requestId), delay);
    }

    async function design(event, queuedRequestId = null) {
      if (event) event.preventDefault();
      window.clearTimeout(designTimer);
      const requestId = queuedRequestId || activeDesignRequest + 1;
      activeDesignRequest = requestId;
      submit.disabled = true;
      submit.textContent = 'Designing...';
      showMessage(errors, '');
      try {
        const response = await fetch('/api/design', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payloadFromForm())
        });
        const result = await response.json();
        if (!response.ok) {
          throw new Error(result.error || 'The CLI request failed.');
        }
        if (requestId !== activeDesignRequest) return;
        renderResult(result);
      } catch (error) {
        if (requestId !== activeDesignRequest) return;
        preview.innerHTML = '<div class="empty">The design could not be generated.</div>';
        showMessage(errors, error.message);
      } finally {
        if (requestId === activeDesignRequest) {
          submit.disabled = false;
          submit.textContent = 'Update now';
        }
      }
    }

    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        currentView = tab.dataset.view;
        renderPreview();
      });
    });
    form.addEventListener('submit', design);
    form.addEventListener('input', () => scheduleDesign());
    form.addEventListener('change', () => scheduleDesign(0));
    design();
  </script>
</body>
</html>
"""


class PlannerRequestHandler(BaseHTTPRequestHandler):
    output_root: Path
    project_root: Path

    server_version = "PIPPlannerHTTP/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_text(HTTPStatus.OK, HTML_PAGE, "text/html; charset=utf-8")
            return

        if parsed.path == "/favicon.ico":
            self._send_bytes(HTTPStatus.NO_CONTENT, b"", "image/x-icon")
            return

        if parsed.path.startswith("/generated/"):
            self._serve_generated(parsed.path)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/design":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found."})
            return

        try:
            payload = self._read_json()
            result = self._run_cli_design(payload)
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except RuntimeError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        self._send_json(HTTPStatus.OK, result)

    def log_message(self, format: str, *args: object) -> None:
        # Keep test and CLI output quiet unless a caller wraps the server logs.
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            raise ValueError("Request body is required.")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON request: {exc.msg}.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request JSON must be an object.")
        return payload

    def _run_cli_design(self, payload: dict) -> dict:
        sequence = str(payload.get("sequence", "")).strip()
        if not sequence:
            raise ValueError("DNA sequence is required.")

        architecture = _choice(payload, "architecture", {"hairpin", "linear"}, "hairpin")
        at_mode = _choice(payload, "at_mode", {"distinguish", "py-py"}, "distinguish")
        tail = _choice(payload, "tail", {"dp", "none"}, "dp")
        turn = _choice(payload, "turn", {"gamma", "beta", "none"}, "gamma")

        safe_name = safe_design_name(sequence, architecture)
        run_id = f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe_name}"
        run_dir = (self.output_root / run_id).resolve()
        run_dir.mkdir(parents=True, exist_ok=True)

        command = [
            *_cli_command_prefix(),
            "design",
            sequence,
            "--architecture",
            architecture,
            "--at-mode",
            at_mode,
            "--tail",
            tail,
            "--turn",
            turn,
            "--out",
            str(run_dir),
            "--name",
            safe_name,
            "--format",
            "json",
        ]

        completed = subprocess.run(
            command,
            cwd=str(self.project_root),
            text=True,
            capture_output=True,
            timeout=20,
        )
        if completed.returncode != 0:
            error = completed.stderr.strip() or completed.stdout.strip() or "CLI command failed."
            raise RuntimeError(error)

        try:
            cli_payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CLI returned invalid JSON: {exc.msg}.") from exc

        files = cli_payload.get("files", {})
        chemical_path = Path(files["chemical_svg"]).resolve()
        schematic_path = Path(files["schematic_svg"]).resolve()
        _assert_within(chemical_path, self.output_root)
        _assert_within(schematic_path, self.output_root)

        return {
            "design": cli_payload,
            "chemical_svg": chemical_path.read_text(encoding="utf-8"),
            "schematic_svg": schematic_path.read_text(encoding="utf-8"),
            "generated": {
                "run_id": run_id,
                "chemical_svg_url": f"/generated/{run_id}/{chemical_path.name}",
                "schematic_svg_url": f"/generated/{run_id}/{schematic_path.name}",
                "chemical_svg_name": chemical_path.name,
                "schematic_svg_name": schematic_path.name,
            },
            "invoked_command": command,
        }

    def _serve_generated(self, path: str) -> None:
        relative = unquote(path.removeprefix("/generated/"))
        if "/" not in relative:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Generated file not found."})
            return

        candidate = (self.output_root / relative).resolve()
        try:
            _assert_within(candidate, self.output_root)
        except ValueError:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "Generated file path is not allowed."})
            return

        if not candidate.exists() or candidate.suffix not in {".svg", ".json"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Generated file not found."})
            return

        content_type = "image/svg+xml; charset=utf-8" if candidate.suffix == ".svg" else "application/json; charset=utf-8"
        self._send_bytes(HTTPStatus.OK, candidate.read_bytes(), content_type)

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8")

    def _send_text(self, status: HTTPStatus, body: str, content_type: str) -> None:
        self._send_bytes(status, body.encode("utf-8"), content_type)

    def _send_bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the PIP Planner local web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface. Default: 127.0.0.1.")
    parser.add_argument("--port", type=int, default=8765, help="Port. Default: 8765.")
    parser.add_argument("--out", default="output/web", help="Directory for UI-generated CLI output files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_root = Path(args.out).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    handler_class = type(
        "ConfiguredPlannerRequestHandler",
        (PlannerRequestHandler,),
        {
            "output_root": output_root,
            "project_root": Path.cwd().resolve(),
        },
    )

    server = ThreadingHTTPServer((args.host, args.port), handler_class)
    print(f"PIP Planner UI running at http://{args.host}:{args.port}/")
    print(f"Generated files will be written under {output_root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PIP Planner UI.")
    finally:
        server.server_close()
    return 0


def _choice(payload: dict, key: str, allowed: set[str], default: str) -> str:
    value = str(payload.get(key, default))
    if value not in allowed:
        raise ValueError(f"{key} must be one of: {', '.join(sorted(allowed))}.")
    return value


def _assert_within(path: Path, root: Path) -> None:
    path.relative_to(root.resolve())


def _cli_command_prefix() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "pip_planner"]


if __name__ == "__main__":
    raise SystemExit(main())
