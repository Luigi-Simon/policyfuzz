"""Real TCP smoke test; the recorded cache never calls a provider."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from app.domain.models import RunView


def test_recorded_workflow_over_real_http():
    root = Path(__file__).resolve().parents[3]
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    environment = {**os.environ, "APP_MODE": "cached"}
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(root / "backend"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(
            base_url=f"http://127.0.0.1:{port}", timeout=5, trust_env=False
        ) as client:
            for _ in range(100):
                assert server.poll() is None, "HTTP application exited during startup"
                try:
                    health = client.get("/api/v1/health")
                    if health.status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.05)
            else:
                raise AssertionError("HTTP application did not become ready")
            created = client.post(
                "/api/v1/runs",
                json={
                    "source_type": "bundled_sample",
                    "title": "Synthetic TCP smoke",
                    "sample_id": "development-policy",
                },
            )
            assert created.status_code == 202
            run_id = created.json()["run_id"]
            response = client.get(f"/api/v1/runs/{run_id}")
            assert response.status_code == 200
            view = RunView.model_validate_json(response.content)
            assert view.stage == "complete"
            assert view.mode == "cached"
            assert view.comparison_metrics is not None
            assert view.comparison_metrics.patch_accepted
            assert client.delete(f"/api/v1/runs/{run_id}").status_code == 200
            assert client.get(f"/api/v1/runs/{run_id}").status_code == 404
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
