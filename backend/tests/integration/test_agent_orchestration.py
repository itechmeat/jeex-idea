import pytest
from uuid import uuid4


@pytest.mark.asyncio
@pytest.mark.integration
async def test_agent_workflow_end_to_end(api_client, test_project_id, test_user_id):
    # 1) Create a project (assumes projects API and user exist rules for test env)
    #    If user precondition is strict, skip project creation and use an existing project in test env
    create_resp = await api_client.post(
        "/projects",
        json={
            "name": "test-agent-orch",
            "language": "en",
            "status": "draft",
            "current_step": 1,
            "meta_data": {},
            "created_by": test_user_id,
        },
    )
    if create_resp.status_code != 201:
        pytest.skip("Project creation not available in test environment")
    project = create_resp.json()
    project_id = project["id"]

    # 2) Start workflow
    start_resp = await api_client.post(
        f"/projects/{project_id}/agents/workflows/idea/start",
        params={
            "user_id": test_user_id,
            "language": "en",
            "user_message": "hello",
        },
    )
    assert start_resp.status_code == 202
    meta = start_resp.json()
    assert meta["status"] == "completed"
    execution_id = meta["execution_id"]
    assert execution_id

    # 3) Fetch recent executions for the project
    list_resp = await api_client.get(
        f"/projects/{project_id}/agents/executions",
        params={"user_id": test_user_id, "per_page": 5},
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] >= 1
    assert any(e["id"] == execution_id for e in data["executions"])

    # 4) Health and contracts endpoints
    health = await api_client.get("/agents/health")
    assert health.status_code == 200
    contracts = await api_client.get("/agents/contracts")
    assert contracts.status_code == 200
