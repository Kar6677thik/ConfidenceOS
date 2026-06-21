"""
Auth guardrail regression tests for protected ConfidenceOS mutations.

These tests prove role authorization uses verified JWTs, not legacy X-Role
headers or actor_role fields in request bodies.
"""


def test_protected_mutation_rejects_missing_token(client):
    response = client.post("/api/studio/build/run")
    assert response.status_code == 401


def test_x_role_header_does_not_authorize_mutation(client):
    response = client.post("/api/studio/build/run", headers={"X-Role": "Engineer"})
    assert response.status_code == 401


def test_wrong_jwt_role_is_forbidden(client, auth_headers):
    response = client.post("/api/studio/build/run", headers=auth_headers("Operator"))
    assert response.status_code == 403


def test_valid_engineer_jwt_allows_studio_build(client, auth_headers):
    response = client.post("/api/studio/build/run", headers=auth_headers("Engineer"))
    assert response.status_code == 200
    assert "build_id" in response.json()


def test_valid_operator_jwt_allows_verification_request(client, auth_headers):
    response = client.post(
        "/api/verification-tokens",
        params={"plant_id": "plant-a"},
        headers=auth_headers("Operator"),
        json={
            "sensor_id": "LT-5100",
            "verification_type": "field_check",
            "valid_minutes": 30,
            "note": "Auth guardrail verification request.",
        },
    )
    assert response.status_code == 200
    assert response.json()["sensor_id"] == "LT-5100"


def test_compliance_report_rejects_missing_token(client):
    response = client.post(
        "/api/compliance/generate",
        json={"plant_id": "plant-a", "hours": 8, "report_type": "full"},
    )
    assert response.status_code == 401


def test_compliance_report_rejects_operator_role(client, auth_headers):
    response = client.post(
        "/api/compliance/generate",
        headers=auth_headers("Operator"),
        json={"plant_id": "plant-a", "hours": 8, "report_type": "full"},
    )
    assert response.status_code == 403


def test_compliance_report_records_authenticated_actor(client, auth_headers):
    response = client.post(
        "/api/compliance/generate",
        headers=auth_headers("Manager"),
        json={"plant_id": "plant-a", "hours": 8, "report_type": "full"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["generated_role"] == "Manager"
    assert payload["generated_by"]
    assert "generated_by" in payload["provenance"]
    assert "report_event_id" in payload
