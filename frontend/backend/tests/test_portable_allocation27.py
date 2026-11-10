"""The real 27-person release request must work before testing proxy transport."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.models import OptimizeRequest


def test_real_release_request_returns_six_valid_activities():
    fixture = Path(__file__).resolve().parents[3] / "packaging/windows/fixtures/allocation27.json"
    payload = json.loads(fixture.read_text())
    request = OptimizeRequest.model_validate(payload)
    assert len(request.participants) == 27
    assert sum(p.attributes["Gender"] == "Male" for p in request.participants) == 14
    client = TestClient(app)
    response = client.post("/api/optimize", json=payload)
    assert response.status_code == 200, response.text
    result = response.json()["allocation"]
    assert result["status"] in {"OPTIMAL", "FEASIBLE"}
    assert {a["activity_id"] for a in result["activities"]} == {"main", "quiz", "team", "bus", "reflection", "hotel"}
    validation = client.post("/api/allocations/validate", json={**payload, "allocation": result})
    assert validation.status_code == 200 and validation.json()["valid"], validation.text
    all_ids = {p["id"] for key in ("participants", "faculty_members", "support_members") for p in payload[key]}
    for activity in result["activities"]:
        ids = [pid for group in activity["groups"] for pid in group["participant_ids"]]
        assert len(ids) == len(set(ids))
        if activity["activity_id"] == "hotel":
            assert set(ids) == all_ids
            assert activity["room_summary"]["total_rooms"] == len(activity["groups"])
        elif activity["activity_id"] == "reflection":
            assert len(activity["sessions"]) == 27
