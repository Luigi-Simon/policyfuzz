from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import SAMPLE_POLICY


def test_docs_zip_download(tmp_settings):
    client = TestClient(create_app())
    response = client.get("/download/api-docs.zip")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    assert "policy-engine-api-docs.zip" in response.headers.get("content-disposition", "")
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_contracts_export(tmp_settings):
    client = TestClient(create_app())
    response = client.get("/v1/contracts")
    body = response.json()
    assert "PolicyIR" in body
    assert "PolicyEffectivenessReport" in body
    assert "ScenarioSuite" in body
    assert body["PolicyIR"]["properties"]["rules"]


def test_create_run_and_fetch_ir(tmp_settings):
    client = TestClient(create_app())
    files = {"file": ("sample_policy.txt", SAMPLE_POLICY.read_bytes(), "text/plain")}
    data = {
        "seed_text": "Urban high school, mixed SES, active PTA",
        "population_size": "80",
        "groups": "students,teachers,parents",
    }
    response = client.post("/v1/runs", files=files, data=data)
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert run["ir"]["rules"]
    assert run["suite"]
    assert run["suite"]["population_size"] == 50
    run_id = run["run_id"]

    ir = client.get(f"/v1/runs/{run_id}/ir")
    assert ir.status_code == 200
    assert ir.json()["index"]["fact_fields"]

    listed = client.get("/v1/runs")
    assert any(item["run_id"] == run_id for item in listed.json())


def test_policyfuzz_linked_run_retains_confirmed_step_one_provenance(tmp_settings):
    client = TestClient(create_app())
    files = {"file": ("sample_policy.txt", SAMPLE_POLICY.read_bytes(), "text/plain")}
    response = client.post(
        "/v1/runs",
        files=files,
        data={
            "policyfuzz_run_id": "public-run-123",
            "policy_ir_sha256": "a" * 64,
            "policy_contract_sha256": "b" * 64,
            "scenario_suite_sha256": "c" * 64,
            "policyfuzz_confirmation": "confirmed",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["extra"]["policyfuzz_confirmation"] == {
        "run_id": "public-run-123",
        "policy_ir_sha256": "a" * 64,
        "policy_contract_sha256": "b" * 64,
        "scenario_suite_sha256": "c" * 64,
        "confirmation": "confirmed",
    }


def test_policyfuzz_linked_run_rejects_partial_provenance(tmp_settings):
    client = TestClient(create_app())
    files = {"file": ("sample_policy.txt", SAMPLE_POLICY.read_bytes(), "text/plain")}
    response = client.post(
        "/v1/runs",
        files=files,
        data={"policyfuzz_run_id": "public-run-123", "policyfuzz_confirmation": "confirmed"},
    )
    assert response.status_code == 400
    assert "all three artifact hashes" in response.text


def test_post_scenarios(tmp_settings):
    client = TestClient(create_app())
    files = {"file": ("sample_policy.txt", SAMPLE_POLICY.read_bytes(), "text/plain")}
    run = client.post("/v1/runs", files=files).json()
    suite = {
        "policy_id": run["ir"]["policy_id"],
        "policy_revision": run["ir"]["revision"],
        "seed": "board of governors",
        "population_size": 12,
        "scenarios": [
            {
                "kind": "adversarial",
                "title": "Medical-device cover story",
                "facts": {"actor.role": "student", "action.name": "use_device", "context.exemption": True},
                "targeted_rule_ids": [run["ir"]["rules"][0]["id"]],
                "expected_outcome": "exception",
            }
        ],
    }
    attached = client.post(f"/v1/runs/{run['run_id']}/scenarios", json=suite)
    assert attached.status_code == 200, attached.text
    assert attached.json()["status"] == "completed"
    fetched = client.get(f"/v1/runs/{run['run_id']}/scenarios")
    assert fetched.json()["scenarios"][0]["kind"] == "adversarial"
    score = client.get(f"/v1/runs/{run['run_id']}/effectiveness")
    assert score.status_code == 200
    assert 0 <= score.json()["score"] <= 100


def test_create_run_from_pasted_policy_text(tmp_settings):
    client = TestClient(create_app())
    response = client.post(
        "/v1/runs",
        data={
            "policy_text": SAMPLE_POLICY.read_text(encoding="utf-8"),
            "seed_text": "Parents and teachers in one district",
            "population_size": "20",
            "groups": "parents,teachers",
        },
    )
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["status"] == "completed"
    assert run["seed"]["groups"] == ["parents", "teachers"]
    assert run["effectiveness"]["swarm_used"] is False


def test_rehearse_without_swarm_keeps_fuzz_score(tmp_settings):
    client = TestClient(create_app())
    files = {"file": ("sample_policy.txt", SAMPLE_POLICY.read_bytes(), "text/plain")}
    run = client.post("/v1/runs", files=files).json()
    response = client.post(f"/v1/runs/{run['run_id']}/rehearse?swarm=false")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["effectiveness"]["swarm_used"] is False
    assert 0 <= body["effectiveness"]["score"] <= 100
    assert body["effectiveness"]["recommended_actions"]
