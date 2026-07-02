from pathlib import Path
import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib import request
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]


class WebApiTests(unittest.TestCase):
    def test_web_api_calls_cli_and_serves_generated_svg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            port = _free_port()
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
                    tmp,
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            try:
                _wait_for_url(f"http://127.0.0.1:{port}/")
                payload = json.dumps(
                    {
                        "sequence": "ATGC",
                        "architecture": "linear",
                        "at_mode": "py-py",
                        "tail": "none",
                        "turn": "gamma",
                    }
                ).encode("utf-8")
                http_request = request.Request(
                    f"http://127.0.0.1:{port}/api/design",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with request.urlopen(http_request, timeout=10) as response:
                    result = json.loads(response.read().decode("utf-8"))

                self.assertIn("-m", result["invoked_command"])
                self.assertEqual(result["design"]["architecture"], "linear")
                self.assertIn("<svg", result["chemical_svg"])
                self.assertIn("data-renderer=\"RDKit\"", result["chemical_svg"])
                self.assertIn("Py-Py-Im-Py", result["design"]["chain_code"])
                self.assertTrue(result["design"]["chemical_renderer"].startswith("RDKit "))
                solubility_methods = {prediction["method"] for prediction in result["design"]["solubility_predictions"]}
                self.assertEqual(solubility_methods, {"ADMET-AI v2", "SolTranNet"})

                with request.urlopen(
                    f"http://127.0.0.1:{port}{result['generated']['chemical_svg_url']}",
                    timeout=10,
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("image/svg+xml", response.headers["Content-Type"])
                    self.assertIn(b"<svg", response.read())
            finally:
                server.terminate()
                try:
                    server.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.communicate(timeout=5)


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
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")


if __name__ == "__main__":
    unittest.main()
