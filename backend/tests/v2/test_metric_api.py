"""Review-before-run integration tests using the real offline Metric service."""

from fastapi.testclient import TestClient

from app.v2.main import create_app


def test_sample_review_run_and_stale_review():
    with TestClient(create_app()) as client:
        sample = client.get("/api/v2/metric/sample")
        assert sample.status_code == 200
        policy = sample.json()
        review = client.post("/api/v2/metric/prepare", json={"policy": policy})
        assert review.status_code == 200
        assert review.json()["status"] == "ready"
        body = {
            "policy": policy,
            "review_fingerprint": review.json()["review_fingerprint"],
        }
        response = client.post("/api/v2/metric/runs", json=body)
        assert response.status_code == 200
        result = response.json()
        assert result["generation_method"] == "rule_templates"
        assert result["failed"] > 0
        assert result["passed"] > 0
        assert (
            len(result["cases"])
            == result["passed"] + result["failed"] + result["unscored"]
        )
        body["policy"]["agent_seed"] += " More cautious."
        stale = client.post("/api/v2/metric/runs", json=body)
        assert stale.status_code == 409
        assert stale.json() == {
            "detail": "Policy inputs changed. Review the policy again."
        }


def test_unsupported_policy_is_not_scored_or_echoed():
    with TestClient(create_app()) as client:
        policy = client.get("/api/v2/metric/sample").json()
        policy["description"] = "Private unsupported prose. 政策"
        review = client.post("/api/v2/metric/prepare", json={"policy": policy})
        assert review.status_code == 200
        assert review.json()["status"] == "needs_clarification"
        assert "Private unsupported prose" not in review.text
        result = client.post(
            "/api/v2/metric/runs",
            json={
                "policy": policy,
                "review_fingerprint": review.json()["review_fingerprint"],
            },
        )
        assert result.status_code == 200
        assert result.json()["cases"] == []
        assert result.json()["pass_rate"] is None


def test_review_fingerprint_is_required_and_bad_inputs_are_safe():
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v2/metric/runs", json={"policy": {"description": "secret"}}
        )
        assert response.status_code == 422
        assert response.json() == {"detail": "Invalid run input."}
