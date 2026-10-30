"""Engineering assistant API and deterministic tool checks."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.agent.retrieval import create_scoped_boundary_layer_search, search_boundary_layer_rules
from app.agent.tools import calculate_smooth_layers, calculate_uniform_first_height
from app.database import Database


def _create_venturi_template(client: TestClient) -> int:
    database: Database = client.app.state.database
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO part_categories(id, name, created_at, updated_at)
               VALUES ('test-venturi', '文丘里', 'now', 'now')"""
        )
        connection.execute(
            """INSERT INTO agent_category_knowledge(category_id, knowledge_source_id, created_at)
               VALUES ('test-venturi', 'venturi-boundary-layer-v2', 'now')"""
        )
        cursor = connection.execute(
            """INSERT INTO meshing_automations(
               name, description, model_family, reference_model_id, workflow_type, preset_json,
               status, created_at, updated_at, category_id)
               VALUES (?, '', '文丘里', NULL, 'watertight', ?, 'draft', 'now', 'now', ?)""",
            (
                "Agent test template",
                json.dumps(
                    {
                        "schema_version": 2,
                        "fluent_version": "25.2",
                        "workflow_type": "watertight",
                        "items": [],
                        "face_label_catalog": [],
                    }
                ),
                "test-venturi",
            ),
        )
        return int(cursor.lastrowid)


def _model_config() -> dict[str, object]:
    return {
        "display_name": "Test model",
        "model_id": "test-model",
        "base_url": "https://example.com/v1",
        "timeout_seconds": 30,
        "enabled": True,
        "connection_status": "passed",
        "tool_status": "passed",
        "vision_status": "untested",
        "streaming_status": "passed",
    }


def test_model_config_and_template_session_are_persisted(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    template_id = _create_venturi_template(app_client)
    response = app_client.put("/api/agent/model", json=_model_config(), headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["model_id"] == "test-model"

    session = app_client.get(f"/api/agent/templates/{template_id}/session", headers=auth_headers)
    assert session.status_code == 200
    assert session.json()["agent_id"] == f"fluent-template-{template_id}"
    assert session.json()["session_id"] == f"fluent-template-session-{template_id}"
    assert session.json()["messages"] == []


def test_proactive_suggestion_uses_real_scoped_retrieval_and_persists_sources(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    template_id = _create_venturi_template(app_client)
    app_client.put("/api/agent/model", json=_model_config(), headers=auth_headers)
    retrieval = create_scoped_boundary_layer_search(
        ("原有_层数推荐算法说明.md", "Uniform_First_Height_计算封装说明.md")
    )
    actual_result = retrieval("Smooth Transition 首层 y+ 外层 y+ 增长率 层数")
    if isinstance(actual_result, str):  # Agno tools return JSON strings
        actual_result = json.loads(actual_result)
    assert actual_result["results"]
    query = actual_result["query"]

    class FakeAgent:
        async def arun(self, *_args, **_kwargs):
            tool = SimpleNamespace(
                tool_name="search_boundary_layer_rules",
                tool_args={"query": query},
                result=actual_result,
            )
            yield SimpleNamespace(event="ToolCallStarted", tool=tool)
            yield SimpleNamespace(event="ToolCallCompleted", tool=tool)
            yield SimpleNamespace(
                event="RunContent",
                content=json.dumps(
                    {
                        "should_suggest": True,
                        "relevance_reason": "检索章节涉及当前阶段需要核对的增长率。",
                        "suggestion": (
                            "检索资料描述了 Smooth Transition 的层数估算假设，可先核对增长率条件。"
                        ),
                        "follow_up_questions": ["当前增长率设为多少？"],
                        "sources": [
                            {
                                "source": actual_result["results"][0]["source"],
                                "section": actual_result["results"][0]["section"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            )

    captured: dict[str, object] = {}

    def build_fake_agent(**kwargs):
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr("app.api.agent.build_agent", build_fake_agent)
    response = app_client.post(
        f"/api/agent/templates/{template_id}/proactive-suggestion",
        json={"stage_key": "add_boundary_layer"},
        headers={**auth_headers, "X-Model-Api-Key": "test-key"},
    )

    assert response.status_code == 200
    suggestion = response.json()
    assert suggestion["should_suggest"] is True
    assert suggestion["sources"] == [
        {
            "source": actual_result["results"][0]["source"],
            "section": actual_result["results"][0]["section"],
        }
    ]
    assert captured["allowed_knowledge_files"] == (
        "Uniform_First_Height_计算封装说明.md",
        "原有_层数推荐算法说明.md",
    )
    session = app_client.get(
        f"/api/agent/templates/{template_id}/session", headers=auth_headers
    ).json()
    assert session["proactive_suggestions"][0]["run_id"] == suggestion["run_id"]
    database: Database = app_client.app.state.database
    with database.connect() as connection:
        event_types = [
            row["event_type"]
            for row in connection.execute(
                "SELECT event_type FROM agent_run_events WHERE run_id = ? ORDER BY id",
                (suggestion["run_id"],),
            ).fetchall()
        ]
        tool_result = connection.execute(
            """SELECT payload_json FROM agent_run_events
               WHERE run_id = ? AND event_type = 'tool_completed'""",
            (suggestion["run_id"],),
        ).fetchone()[0]
    assert "proactive_context" in event_types
    assert "tool_started" in event_types
    assert "tool_completed" in event_types
    assert "relevance_assessed" in event_types
    assert actual_result["results"][0]["source"] in tool_result


def test_proactive_suggestion_is_suppressed_for_empty_knowledge_and_unconfigured_model(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    template_id = _create_venturi_template(app_client)
    database: Database = app_client.app.state.database
    with database.connect() as connection:
        connection.execute(
            "DELETE FROM agent_category_knowledge WHERE category_id = 'test-venturi'"
        )

    def unexpected_build(**_kwargs):
        raise AssertionError("空知识库和未配置模型都不应启动 Agent")

    monkeypatch.setattr("app.api.agent.build_agent", unexpected_build)
    no_model = app_client.post(
        f"/api/agent/templates/{template_id}/proactive-suggestion",
        json={"stage_key": "page_open"},
        headers=auth_headers,
    )
    assert no_model.status_code == 200
    assert no_model.json() is None

    app_client.put("/api/agent/model", json=_model_config(), headers=auth_headers)
    empty_knowledge = app_client.post(
        f"/api/agent/templates/{template_id}/proactive-suggestion",
        json={"stage_key": "page_open"},
        headers={**auth_headers, "X-Model-Api-Key": "test-key"},
    )
    assert empty_knowledge.status_code == 200
    assert empty_knowledge.json() is None
    session = app_client.get(
        f"/api/agent/templates/{template_id}/session", headers=auth_headers
    ).json()
    assert session["proactive_suggestions"] == []


def test_proactive_suggestion_requires_a_citation_from_the_retrieval_result(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    template_id = _create_venturi_template(app_client)
    app_client.put("/api/agent/model", json=_model_config(), headers=auth_headers)
    retrieval = create_scoped_boundary_layer_search(
        ("原有_层数推荐算法说明.md", "Uniform_First_Height_计算封装说明.md")
    )
    actual_result = retrieval("Uniform First Height 密度 动力黏度 特征速度 水力直径")
    if isinstance(actual_result, str):  # Agno tools return JSON strings
        actual_result = json.loads(actual_result)

    class FakeAgent:
        async def arun(self, *_args, **_kwargs):
            tool = SimpleNamespace(
                tool_name="search_boundary_layer_rules",
                tool_args={"query": actual_result["query"]},
                result=actual_result,
            )
            yield SimpleNamespace(event="ToolCallStarted", tool=tool)
            yield SimpleNamespace(event="ToolCallCompleted", tool=tool)
            yield SimpleNamespace(
                event="RunContent",
                content=json.dumps(
                    {
                        "should_suggest": True,
                        "suggestion": "无依据建议",
                        "sources": [{"source": "invented.md", "section": "虚构章节"}],
                    },
                ),
            )

    monkeypatch.setattr("app.api.agent.build_agent", lambda **_kwargs: FakeAgent())
    response = app_client.post(
        f"/api/agent/templates/{template_id}/proactive-suggestion",
        json={"stage_key": "add_boundary_layer"},
        headers={**auth_headers, "X-Model-Api-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json() is None
    history = app_client.get(
        f"/api/agent/templates/{template_id}/session", headers=auth_headers
    ).json()
    assert history["proactive_suggestions"] == []


def test_proactive_suggestion_stays_empty_when_associated_knowledge_is_irrelevant(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    template_id = _create_venturi_template(app_client)
    app_client.put("/api/agent/model", json=_model_config(), headers=auth_headers)
    retrieval = create_scoped_boundary_layer_search(
        ("原有_层数推荐算法说明.md", "Uniform_First_Height_计算封装说明.md")
    )
    actual_result = retrieval("太阳能电池的电路板颜色")
    if isinstance(actual_result, str):  # Agno tools return JSON strings
        actual_result = json.loads(actual_result)
    assert actual_result["status"] == "no_match"

    class FakeAgent:
        async def arun(self, *_args, **_kwargs):
            tool = SimpleNamespace(
                tool_name="search_boundary_layer_rules",
                tool_args={"query": actual_result["query"]},
                result=actual_result,
            )
            yield SimpleNamespace(event="ToolCallStarted", tool=tool)
            yield SimpleNamespace(event="ToolCallCompleted", tool=tool)
            yield SimpleNamespace(
                event="RunContent",
                content=json.dumps(
                    {"should_suggest": False, "suggestion": "", "sources": []},
                ),
            )

    monkeypatch.setattr("app.api.agent.build_agent", lambda **_kwargs: FakeAgent())
    response = app_client.post(
        f"/api/agent/templates/{template_id}/proactive-suggestion",
        json={"stage_key": "add_boundary_layer"},
        headers={**auth_headers, "X-Model-Api-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json() is None
    history = app_client.get(
        f"/api/agent/templates/{template_id}/session", headers=auth_headers
    ).json()
    assert history["proactive_suggestions"] == []


def test_chat_stream_persists_messages_and_run_events(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    template_id = _create_venturi_template(app_client)
    app_client.put("/api/agent/model", json=_model_config(), headers=auth_headers)
    image_bytes = b"\x89PNG\r\n\x1a\nimage-data"
    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    received_images = []

    class FakeAgent:
        async def arun(self, *_args, **kwargs):
            received_images.extend(kwargs.get("images") or [])
            tool = SimpleNamespace(
                tool_name="calculate_smooth_layers",
                tool_args={"first_cell_y_plus": 1},
                result={"recommended_layers": 10},
            )
            yield SimpleNamespace(event="ToolCallStarted", tool=tool)
            yield SimpleNamespace(event="RunContent", content="建议先比较两种边界层方法。")
            yield SimpleNamespace(event="ToolCallCompleted", tool=tool)

    monkeypatch.setattr("app.api.agent.build_agent", lambda **_kwargs: FakeAgent())
    response = app_client.post(
        f"/api/agent/templates/{template_id}/messages",
        json={
            "message": "请比较两种方法",
            "client_message_id": "request-1",
            "images": [
                {
                    "filename": "boundary-layer.png",
                    "mime_type": "image/png",
                    "data_base64": encoded_image,
                }
            ],
        },
        headers={**auth_headers, "X-Model-Api-Key": "test-key"},
    )
    assert response.status_code == 200
    assert '"type":"started"' in response.text
    assert "建议先比较两种边界层方法。" in response.text
    assert '"tool_status":"running"' in response.text
    assert '"tool_status":"completed"' in response.text
    assert '"type":"completed"' in response.text
    assert len(received_images) == 1
    assert received_images[0].content == image_bytes

    history = app_client.get(
        f"/api/agent/templates/{template_id}/session", headers=auth_headers
    ).json()
    assert [message["role"] for message in history["messages"]] == [
        "user",
        "assistant",
        "assistant",
        "assistant",
    ]
    assert history["messages"][1]["tool_name"] == "calculate_smooth_layers"
    assert history["messages"][1]["tool_status"] == "running"
    assert history["messages"][2]["tool_status"] == "completed"
    assert history["messages"][3]["content"] == "建议先比较两种边界层方法。"
    assert history["messages"][0]["attachments"][0]["filename"] == "boundary-layer.png"
    assert history["messages"][0]["attachments"][0]["data_base64"] == encoded_image

    repeated = app_client.post(
        f"/api/agent/templates/{template_id}/messages",
        json={"message": "请比较两种方法", "client_message_id": "request-1"},
        headers={**auth_headers, "X-Model-Api-Key": "test-key"},
    )
    assert repeated.status_code == 409


def test_capability_test_requires_a_real_tool_result(
    app_client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    class FakeAgent:
        async def arun(self, *_args, **_kwargs):
            yield SimpleNamespace(
                event="ToolCallCompleted",
                tool=SimpleNamespace(result={"recommended_layers": 10}),
            )
            yield SimpleNamespace(event="RunContent", content="10 层")

    monkeypatch.setattr("app.api.agent.build_agent", lambda **_kwargs: FakeAgent())
    response = app_client.post(
        "/api/agent/model/capabilities",
        json={
            "display_name": "Test model",
            "model_id": "test-model",
            "base_url": "https://example.com/v1",
            "timeout_seconds": 30,
        },
        headers={**auth_headers, "X-Model-Api-Key": "test-key"},
    )
    assert response.status_code == 200
    assert response.json()["tool_status"] == "passed"
    assert response.json()["streaming_status"] == "passed"


def test_smooth_and_uniform_tools_return_source_algorithm_outputs() -> None:
    smooth = calculate_smooth_layers(1, 50, 1.2)
    assert smooth["recommended_layers"] == 10
    assert smooth["nominal_outer_y_plus"] == 51.917364

    uniform = calculate_uniform_first_height(
        density_kg_m3=998,
        dynamic_viscosity_pa_s=0.001,
        characteristic_velocity_m_s=2,
        hydraulic_diameter_mm=50,
        target_first_cell_y_plus=1,
    )
    assert uniform["status"] == "INITIAL_ESTIMATE_NOT_SOLVER_VALIDATED"
    assert round(float(uniform["recommended_first_height_mm"]), 8) == 0.02125505


def test_uniform_out_of_range_requires_confirmation_before_height() -> None:
    inputs = {
        "density_kg_m3": 998,
        "dynamic_viscosity_pa_s": 0.001,
        "characteristic_velocity_m_s": 20,
        "hydraulic_diameter_mm": 50,
        "target_first_cell_y_plus": 1,
    }
    guarded = calculate_uniform_first_height(**inputs)
    assert guarded["confirmation_required"] is True
    assert "recommended_first_height_mm" not in guarded

    accepted = calculate_uniform_first_height(**inputs, allow_out_of_range=True)
    assert accepted["status"] == "INITIAL_ESTIMATE_NOT_SOLVER_VALIDATED"


def test_local_boundary_layer_retrieval_returns_cited_rule_sections() -> None:
    layer_rules = search_boundary_layer_rules("为什么外侧 y+ 目标是 50 1 50 1.2 怎么得到层数")
    assert layer_rules["status"] == "matched"
    assert any(
        result["source"] == "原有_层数推荐算法说明.md" and "为什么选择 50" in result["section"]
        for result in layer_rules["results"]
    )

    uniform_rules = search_boundary_layer_rules(
        "Uniform First Height 密度 动力黏度 特征速度 水力直径"
    )
    assert uniform_rules["status"] == "matched"
    assert any(
        result["source"] == "Uniform_First_Height_计算封装说明.md"
        for result in uniform_rules["results"]
    )


def test_category_capabilities_returns_real_bindings(
    app_client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    _create_venturi_template(app_client)

    response = app_client.get(
        "/api/agent/categories/test-venturi/capabilities", headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["category_id"] == "test-venturi"
    assert [item["id"] for item in payload["knowledge"]] == ["venturi-boundary-layer-v2"]
    assert payload["knowledge"][0]["status"] == "enabled"
    assert len(payload["knowledge"][0]["files"]) == 2
    tool_names = {tool["name"] for tool in payload["tools"]}
    assert tool_names == {"calculate_smooth_layers", "calculate_uniform_first_height"}
    assert all(tool["status"] == "enabled" for tool in payload["tools"])
    assert payload["rules"] == []

    empty = app_client.get("/api/agent/categories/uncategorized/capabilities", headers=auth_headers)
    assert empty.status_code == 200
    assert empty.json() == {
        "category_id": "uncategorized",
        "knowledge": [],
        "rules": [],
        "tools": [],
    }

    missing = app_client.get("/api/agent/categories/no-such/capabilities", headers=auth_headers)
    assert missing.status_code == 404
