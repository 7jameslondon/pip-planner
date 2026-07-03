from pathlib import Path
import json
import os
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
            env = os.environ.copy()
            env["PIP_PLANNER_GENOME_DIR"] = str(ROOT / "tests" / "fixtures" / "genomes")
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
                env=env,
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
                        "genome": "human-grch38",
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
                self.assertIn("--genome", result["invoked_command"])
                self.assertEqual(result["design"]["architecture"], "linear")
                self.assertIn("<svg", result["chemical_svg"])
                self.assertIn("data-renderer=\"RDKit\"", result["chemical_svg"])
                self.assertIn("Py-Py-Im-Py", result["design"]["chain_code"])
                self.assertTrue(result["design"]["chemical_renderer"].startswith("RDKit "))
                solubility_methods = {prediction["method"] for prediction in result["design"]["solubility_predictions"]}
                self.assertEqual(solubility_methods, {"ADMET-AI v2", "SolTranNet"})
                self.assertEqual(result["design"]["genome_occurrences"]["total_occurrences"], 2)
                self.assertEqual(result["design"]["model_3d"]["dna_force_field"], "AMBER DNA.OL24")
                self.assertIn("model_html_url", result["generated"])
                self.assertIn("complex_pdb_url", result["generated"])

                with request.urlopen(
                    f"http://127.0.0.1:{port}{result['generated']['chemical_svg_url']}",
                    timeout=10,
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("image/svg+xml", response.headers["Content-Type"])
                    self.assertIn(b"<svg", response.read())

                with request.urlopen(
                    f"http://127.0.0.1:{port}{result['generated']['complex_pdb_url']}",
                    timeout=10,
                ) as response:
                    self.assertEqual(response.status, 200)
                    self.assertIn("chemical/x-pdb", response.headers["Content-Type"])
                    self.assertIn(b"PIP PLANNER DNA POLYAMIDE", response.read())

                product_payload = json.dumps(
                    {
                        "sequence": "ATGC",
                        "architecture": "linear",
                        "at_mode": "py-py",
                        "tail": "none",
                        "turn": "gamma",
                        "genome": "none",
                        "product": "schematic",
                    }
                ).encode("utf-8")
                product_request = request.Request(
                    f"http://127.0.0.1:{port}/api/design/product",
                    data=product_payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with request.urlopen(product_request, timeout=10) as response:
                    schematic_result = json.loads(response.read().decode("utf-8"))

                self.assertEqual(schematic_result["product"], "schematic")
                self.assertIn("--product", schematic_result["invoked_command"])
                self.assertIn("<svg", schematic_result["schematic_svg"])
                self.assertIn("schematic_svg_url", schematic_result["generated"])

                chemical_payload = json.dumps(
                    {
                        "sequence": "ATGC",
                        "architecture": "linear",
                        "at_mode": "py-py",
                        "tail": "none",
                        "turn": "gamma",
                        "genome": "none",
                        "product": "chemical",
                        "run_id": schematic_result["run_id"],
                    }
                ).encode("utf-8")
                chemical_request = request.Request(
                    f"http://127.0.0.1:{port}/api/design/product",
                    data=chemical_payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with request.urlopen(chemical_request, timeout=10) as response:
                    chemical_result = json.loads(response.read().decode("utf-8"))

                self.assertEqual(chemical_result["product"], "chemical")
                self.assertEqual(chemical_result["run_id"], schematic_result["run_id"])
                self.assertIn("<svg", chemical_result["chemical_svg"])
                self.assertIn("chemical_svg_url", chemical_result["generated"])
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
