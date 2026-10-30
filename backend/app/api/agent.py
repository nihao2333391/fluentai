"""Global model configuration and template-scoped Agno Agent APIs."""

from __future__ import annotations

import asyncio
import base64
import json
import sqlite3
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from app.agent.runtime import build_agent
from app.agent.schemas import (
    AgentCapabilityTestResult,
    AgentChatRequest,
    AgentImageAttachment,
    AgentMessageRead,
    AgentModelConfig,
    AgentModelTestRequest,
    AgentProactiveOutput,
    AgentProactiveRequest,
    AgentProactiveSuggestionRead,
    AgentSessionRead,
    CategoryCapabilitiesRead,
    CategoryCapabilityKnowledgeRead,
    CategoryCapabilityToolRead,
)
from app.api.deps import DatabaseDependency
from app.database import Database
from app.repositories.common import utc_now

router = APIRouter(prefix="/agent", tags=["agent"])
CONFIG_KEY = "agent_model_config"
ALLOWED_KNOWLEDGE_FILES = {
    "原有_层数推荐算法说明.md",
    "Uniform_First_Height_计算封装说明.md",
}
ALLOWED_BOUNDARY_TOOLS = {
    "calculate_smooth_layers",
    "calculate_uniform_first_height",
}
APPROVED_TOOL_DISPLAY_NAMES = {
    "calculate_smooth_layers": "Smooth 层数推荐",
    "calculate_uniform_first_height": "Uniform 首层高度计算",
}


def _get_config(database: Database) -> AgentModelConfig:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?", (CONFIG_KEY,)
        ).fetchone()
    if row is None:
        return AgentModelConfig()
    try:
        return AgentModelConfig.model_validate_json(str(row["value"]))
    except ValueError:
        return AgentModelConfig()


def _save_config(database: Database, config: AgentModelConfig) -> AgentModelConfig:
    now = utc_now()
    serialized = config.model_dump_json()
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO app_settings(key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE
               SET value = excluded.value, updated_at = excluded.updated_at""",
            (CONFIG_KEY, serialized, now),
        )
    return config


def _get_template_session(database: Database, template_id: int) -> tuple[str, str]:
    with database.connect() as connection:
        template = connection.execute(
            "SELECT id FROM meshing_automations WHERE id = ?",
            (template_id,),
        ).fetchone()
        if template is None:
            raise HTTPException(status_code=404, detail="模板不存在；请先保存模板草稿。")
        identity = connection.execute(
            "SELECT agno_agent_id, agno_session_id FROM agent_templates WHERE template_id = ?",
            (template_id,),
        ).fetchone()
        if identity is None:
            agent_id = f"fluent-template-{template_id}"
            session_id = f"fluent-template-session-{template_id}"
            now = utc_now()
            connection.execute(
                """INSERT INTO agent_templates(template_id, agno_agent_id, agno_session_id,
                   created_at, updated_at) VALUES (?, ?, ?, ?, ?)""",
                (template_id, agent_id, session_id, now, now),
            )
        else:
            agent_id = str(identity["agno_agent_id"])
            session_id = str(identity["agno_session_id"])
        return agent_id, session_id


def _get_template_agent_context(database: Database, template_id: int) -> dict[str, Any]:
    with database.connect() as connection:
        row = connection.execute(
            """SELECT a.name AS template_name, c.id AS category_id, c.name AS category_name
               FROM meshing_automations a
               LEFT JOIN part_categories c ON c.id = a.category_id
               WHERE a.id = ?""",
            (template_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="模板不存在；请先保存模板草稿。")
        knowledge_rows = connection.execute(
            """SELECT s.source_files_json, s.allowed_tools_json
               FROM agent_category_knowledge a
               JOIN agent_knowledge_sources s ON s.id = a.knowledge_source_id
               WHERE a.category_id = ? AND s.enabled = 1""",
            (row["category_id"],),
        ).fetchall()

    knowledge_files: set[str] = set()
    allowed_tools: set[str] = set()
    for knowledge_row in knowledge_rows:
        try:
            source_files = json.loads(str(knowledge_row["source_files_json"]))
            tool_names = json.loads(str(knowledge_row["allowed_tools_json"]))
        except json.JSONDecodeError:
            continue
        knowledge_files.update(
            source
            for source in source_files
            if isinstance(source, str) and source in ALLOWED_KNOWLEDGE_FILES
        )
        allowed_tools.update(
            name for name in tool_names if isinstance(name, str) and name in ALLOWED_BOUNDARY_TOOLS
        )
    return {
        "template_name": str(row["template_name"]),
        "category_name": str(row["category_name"] or ""),
        "knowledge_files": tuple(sorted(knowledge_files)),
        "allowed_tools": tuple(sorted(allowed_tools)),
    }


def _sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _event_name(event: Any) -> str:
    raw_name = getattr(event, "event", "")
    return "".join(
        character.lower()
        for character in str(getattr(raw_name, "value", raw_name))
        if character.isalnum()
    )


def _record_event(
    database: Database,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO agent_run_events(run_id, event_type, payload_json, created_at)
               VALUES (?, ?, ?, ?)""",
            (run_id, event_type, json.dumps(payload, ensure_ascii=False), utc_now()),
        )


def _tool_event_content(event_payload: dict[str, Any]) -> str:
    """Return tool args/result as a single JSON string for the session message list.

    工具结果本身已是 JSON 字符串时原样返回，避免双重编码；
    非字符串或非法 JSON 时再序列化，保证输出始终可被前端解析。
    """
    raw = event_payload.get("result", event_payload.get("tool_args", {}))
    if isinstance(raw, str):
        try:
            json.loads(raw)
            return raw
        except json.JSONDecodeError:
            return json.dumps(raw, ensure_ascii=False)
    return json.dumps(raw, ensure_ascii=False)


@router.get("/model", response_model=AgentModelConfig)
def read_model_config(database: DatabaseDependency) -> AgentModelConfig:
    return _get_config(database)


@router.get("/categories/{category_id}/capabilities", response_model=CategoryCapabilitiesRead)
def read_category_capabilities(
    category_id: str, database: DatabaseDependency
) -> CategoryCapabilitiesRead:
    """Read-only capability inventory for the Extension Workspace (V1).

    Returns the real knowledge sources bound to the category plus the approved
    calculation tools they unlock. No rule entities exist yet, so rules is empty.
    """
    with database.connect() as connection:
        category = connection.execute(
            "SELECT id FROM part_categories WHERE id = ?", (category_id,)
        ).fetchone()
        if category is None:
            raise HTTPException(status_code=404, detail="零件目录不存在。")
        rows = connection.execute(
            """SELECT s.id, s.display_name, s.source_files_json, s.allowed_tools_json,
                      s.enabled, s.created_at
               FROM agent_category_knowledge a
               JOIN agent_knowledge_sources s ON s.id = a.knowledge_source_id
               WHERE a.category_id = ?
               ORDER BY s.created_at, s.id""",
            (category_id,),
        ).fetchall()

    knowledge: list[CategoryCapabilityKnowledgeRead] = []
    tools: dict[str, CategoryCapabilityToolRead] = {}
    for row in rows:
        try:
            source_files = json.loads(str(row["source_files_json"]))
            tool_names = json.loads(str(row["allowed_tools_json"]))
        except json.JSONDecodeError:
            source_files, tool_names = [], []
        source_enabled = row["enabled"] == 1
        visible_files = [
            str(source)
            for source in source_files
            if isinstance(source, str) and source in ALLOWED_KNOWLEDGE_FILES
        ]
        knowledge.append(
            CategoryCapabilityKnowledgeRead(
                id=str(row["id"]),
                name=str(row["display_name"]),
                files=visible_files,
                status="enabled" if source_enabled else "disabled",
                created_at=str(row["created_at"]),
            )
        )
        if not source_enabled:
            continue
        for tool_name in tool_names:
            if not isinstance(tool_name, str) or tool_name not in ALLOWED_BOUNDARY_TOOLS:
                continue
            if tool_name not in tools:
                tools[tool_name] = CategoryCapabilityToolRead(
                    name=tool_name,
                    display_name=APPROVED_TOOL_DISPLAY_NAMES.get(tool_name, tool_name),
                    status="enabled",
                    source=str(row["display_name"]),
                )

    return CategoryCapabilitiesRead(
        category_id=category_id,
        knowledge=knowledge,
        rules=[],
        tools=sorted(tools.values(), key=lambda tool: tool.name),
    )


@router.put("/model", response_model=AgentModelConfig)
def write_model_config(payload: AgentModelConfig, database: DatabaseDependency) -> AgentModelConfig:
    try:
        payload.validate_endpoint()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _save_config(database, payload)


@router.post("/model/test")
async def test_model_config(
    payload: AgentModelTestRequest,
    database: DatabaseDependency,
    x_model_api_key: str = Header(default=""),
) -> dict[str, str]:
    if not x_model_api_key.strip():
        raise HTTPException(status_code=400, detail="请先安全保存 API Key。")
    config = payload.model_dump()
    try:
        agent = build_agent(
            config=config,
            api_key=x_model_api_key,
            database_path=database.path,
            agent_id="fluent-model-connection-test",
            tools_enabled=False,
        )
        result = await agent.arun("请仅回复：连接成功。", stream=False)
        content = str(getattr(result, "content", "") or "").strip()
        run_status = getattr(result, "status", None)
        if run_status is not None and (
            str(getattr(run_status, "value", run_status)).upper() == "ERROR"
        ):
            # Agno swallows provider errors into RunOutput.content; surface them as failures.
            raise RuntimeError(f"模型接口返回错误：{content or '未返回错误详情'}")
        if not content:
            raise RuntimeError("模型没有返回文本。")
    except Exception as exc:  # provider errors vary across compatible APIs
        raise HTTPException(status_code=502, detail=f"模型连接测试失败：{exc}") from exc

    return {"status": "passed", "message": content[:500]}


@router.post("/model/capabilities", response_model=AgentCapabilityTestResult)
async def test_model_capabilities(
    payload: AgentModelTestRequest,
    database: DatabaseDependency,
    x_model_api_key: str = Header(default=""),
) -> AgentCapabilityTestResult:
    if not x_model_api_key.strip():
        raise HTTPException(status_code=400, detail="请先安全保存 API Key。")
    agent = build_agent(
        config=payload.model_dump(),
        api_key=x_model_api_key,
        database_path=database.path,
        agent_id="fluent-model-capability-test",
        tools_enabled=True,
    )
    tool_passed = False
    stream_passed = False
    run_error = ""
    try:
        async for event in agent.arun(
            "请调用 calculate_smooth_layers 工具，参数为 first_cell_y_plus=1, "
            "target_outer_y_plus=50, growth_rate=1.2。完成后简短回复层数。",
            stream=True,
            stream_events=True,
        ):
            event_name = _event_name(event)
            if event_name == "runerror":
                run_error = str(getattr(event, "content", "") or "模型运行出错。")
            if "runcontent" in event_name and getattr(event, "content", None):
                stream_passed = True
            if "toolcallcompleted" not in event_name:
                continue
            tool = getattr(event, "tool", None)
            result = getattr(tool, "result", None)
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    result = None
            if isinstance(result, dict) and result.get("recommended_layers") == 10:
                tool_passed = True
    except Exception as exc:
        return AgentCapabilityTestResult(
            tool_status="failed",
            streaming_status="failed",
            message=f"能力测试失败：{str(exc)[:1_000]}",
        )
    if run_error:
        return AgentCapabilityTestResult(
            tool_status="failed",
            streaming_status="failed",
            message=f"模型接口返回错误：{run_error[:1_000]}",
        )
    return AgentCapabilityTestResult(
        tool_status="passed" if tool_passed else "unsupported",
        streaming_status="passed" if stream_passed else "unsupported",
        message=(
            "受控 Smooth 工具返回 10 层，且收到流式文本事件。"
            if tool_passed and stream_passed
            else "模型未完成受控工具调用或没有返回流式文本；普通对话仍可使用。"
        ),
    )


@router.get("/templates/{template_id}/session", response_model=AgentSessionRead)
def read_session(template_id: int, database: DatabaseDependency) -> AgentSessionRead:
    agent_id, session_id = _get_template_session(database, template_id)
    with database.connect() as connection:
        rows = connection.execute(
            """SELECT id, user_message, assistant_message, status, created_at,
                      run_kind, trigger_key, response_json
               FROM agent_runs WHERE template_id = ? ORDER BY created_at, id""",
            (template_id,),
        ).fetchall()
        event_rows = connection.execute(
            """SELECT e.id, e.run_id, e.event_type, e.payload_json, e.created_at
               FROM agent_run_events e JOIN agent_runs r ON r.id = e.run_id
               WHERE r.template_id = ? ORDER BY e.id""",
            (template_id,),
        ).fetchall()
    events_by_run: dict[str, list[sqlite3.Row]] = {}
    images_by_run: dict[str, list[AgentImageAttachment]] = {}
    needs_range_confirmation = False
    for event_row in event_rows:
        run_key = str(event_row["run_id"])
        events_by_run.setdefault(run_key, []).append(event_row)
        try:
            event_payload = json.loads(str(event_row["payload_json"]))
        except json.JSONDecodeError:
            event_payload = {}
        if event_row["event_type"] == "confirmation_required":
            needs_range_confirmation = True
        if event_row["event_type"] == "user_images":
            images_by_run[run_key] = [
                AgentImageAttachment.model_validate(image)
                for image in event_payload.get("images", [])
            ]
        if (
            event_row["event_type"] == "started"
            and event_payload.get("confirm_out_of_range") is True
        ):
            needs_range_confirmation = False
    messages: list[AgentMessageRead] = []
    proactive_suggestions: list[AgentProactiveSuggestionRead] = []
    for row in rows:
        run_key = str(row["id"])
        if row["run_kind"] == "proactive":
            try:
                suggestion = AgentProactiveOutput.model_validate_json(str(row["response_json"]))
            except ValueError:
                suggestion = AgentProactiveOutput()
            if suggestion.should_suggest:
                execution_records: list[dict[str, object]] = []
                for event_row in events_by_run.get(run_key, []):
                    event_type = str(event_row["event_type"])
                    if event_type == "relevance_assessed":
                        try:
                            assessment = json.loads(str(event_row["payload_json"]))
                        except json.JSONDecodeError:
                            assessment = {}
                        execution_records.append(
                            {
                                "tool_name": "相关性判断",
                                "status": "completed",
                                "target": {"sources": assessment.get("sources", [])},
                                "result": {
                                    "should_suggest": assessment.get("should_suggest", False),
                                    "relevance_reason": assessment.get("relevance_reason", ""),
                                },
                            }
                        )
                        continue
                    if event_type not in {"tool_started", "tool_completed"}:
                        continue
                    try:
                        execution_payload = json.loads(str(event_row["payload_json"]))
                    except json.JSONDecodeError:
                        execution_payload = {}
                    tool_name = str(execution_payload.get("tool_name", "工具"))
                    if event_type == "tool_started":
                        execution_records.append(
                            {
                                "tool_name": tool_name,
                                "status": "running",
                                "target": execution_payload.get("tool_args", {}),
                                "result": "",
                            }
                        )
                    else:
                        running_record = next(
                            (
                                item
                                for item in reversed(execution_records)
                                if item["tool_name"] == tool_name and item["status"] == "running"
                            ),
                            None,
                        )
                        if running_record is None:
                            execution_records.append(
                                {
                                    "tool_name": tool_name,
                                    "status": "completed",
                                    "target": {},
                                    "result": execution_payload.get("result", ""),
                                }
                            )
                        else:
                            running_record["status"] = "completed"
                            running_record["result"] = execution_payload.get("result", "")
                proactive_suggestions.append(
                    AgentProactiveSuggestionRead(
                        **suggestion.model_dump(),
                        run_id=run_key,
                        stage_key=str(row["trigger_key"] or "page_open"),
                        execution_records=execution_records,
                        created_at=str(row["created_at"]),
                    )
                )
            continue
        messages.append(
            AgentMessageRead(
                id=f"{row['id']}:user",
                role="user",
                content=str(row["user_message"]),
                run_id=str(row["id"]),
                status=str(row["status"]),
                created_at=str(row["created_at"]),
                attachments=images_by_run.get(run_key, []),
            )
        )
        for event_row in events_by_run.get(run_key, []):
            event_type = str(event_row["event_type"])
            if not event_type.startswith("tool_"):
                continue
            try:
                event_payload = json.loads(str(event_row["payload_json"]))
            except json.JSONDecodeError:
                event_payload = {}
            messages.append(
                AgentMessageRead(
                    id=f"tool:{event_row['id']}",
                    role="assistant",
                    content=_tool_event_content(event_payload),
                    run_id=run_key,
                    status=str(row["status"]),
                    created_at=str(event_row["created_at"]),
                    tool_name=str(event_payload.get("tool_name", "计算工具")),
                    tool_status="running" if event_type == "tool_started" else "completed",
                )
            )
        for event_row in events_by_run.get(run_key, []):
            if event_row["event_type"] == "confirmation_required":
                try:
                    event_payload = json.loads(str(event_row["payload_json"]))
                except json.JSONDecodeError:
                    event_payload = {}
                messages.append(
                    AgentMessageRead(
                        id=f"confirmation:{event_row['id']}",
                        role="assistant",
                        content=json.dumps(event_payload, ensure_ascii=False),
                        run_id=run_key,
                        status=str(row["status"]),
                        created_at=str(event_row["created_at"]),
                        tool_name=str(event_payload.get("tool_name", "Uniform")),
                        tool_status="confirmation_required",
                    )
                )
        assistant = str(row["assistant_message"] or "")
        if assistant:
            messages.append(
                AgentMessageRead(
                    id=f"{row['id']}:assistant",
                    role="assistant",
                    content=assistant,
                    run_id=str(row["id"]),
                    status=str(row["status"]),
                    created_at=str(row["created_at"]),
                )
            )
    return AgentSessionRead(
        template_id=template_id,
        agent_id=agent_id,
        session_id=session_id,
        messages=messages,
        needs_range_confirmation=needs_range_confirmation,
        proactive_suggestions=proactive_suggestions,
    )


@router.post(
    "/templates/{template_id}/proactive-suggestion",
    response_model=AgentProactiveSuggestionRead | None,
)
async def generate_proactive_suggestion(
    template_id: int,
    payload: AgentProactiveRequest,
    database: DatabaseDependency,
    x_model_api_key: str = Header(default=""),
) -> AgentProactiveSuggestionRead | None:
    config = _get_config(database)
    if (
        not config.enabled
        or config.connection_status != "passed"
        or config.tool_status != "passed"
        or not x_model_api_key.strip()
    ):
        return None

    agent_id, chat_session_id = _get_template_session(database, template_id)
    context = _get_template_agent_context(database, template_id)
    knowledge_files = context["knowledge_files"]
    allowed_tools = context["allowed_tools"]
    if not knowledge_files:
        return None

    trigger_key = payload.stage_key.strip()
    with database.connect() as connection:
        existing = connection.execute(
            "SELECT id, status FROM agent_runs WHERE template_id = ? AND trigger_key = ?",
            (template_id, trigger_key),
        ).fetchone()
    if existing is not None:
        if existing["status"] == "completed":
            session = read_session(template_id, database)
            return next(
                (item for item in session.proactive_suggestions if item.run_id == existing["id"]),
                None,
            )
        return None

    run_id = str(uuid.uuid4())
    now = utc_now()
    try:
        with database.connect() as connection:
            connection.execute(
                """INSERT INTO agent_runs(
                       id, template_id, agno_session_id, client_message_id, status,
                       user_message, created_at, model_snapshot_json, run_kind, trigger_key
                   ) VALUES (?, ?, ?, ?, 'running', '', ?, ?, 'proactive', ?)""",
                (
                    run_id,
                    template_id,
                    chat_session_id,
                    f"proactive:{trigger_key}",
                    now,
                    config.model_dump_json(),
                    trigger_key,
                ),
            )
    except sqlite3.IntegrityError:
        return None

    accumulated = ""
    final_content = ""
    retrieved_citations: set[tuple[str, str]] = set()
    _record_event(
        database,
        run_id,
        "proactive_context",
        {
            "stage_key": trigger_key,
            "template_name": context["template_name"],
            "category_name": context["category_name"],
            "knowledge_files": knowledge_files,
            "allowed_tools": allowed_tools,
        },
    )
    try:
        agent = build_agent(
            config=config.model_dump(),
            api_key=x_model_api_key,
            database_path=database.path,
            agent_id=agent_id,
            tools_enabled=True,
            allowed_knowledge_files=knowledge_files,
            allowed_tool_names=allowed_tools,
        )
        proactive_context_json = json.dumps(
            {
                "template_name": context["template_name"],
                "category_name": context["category_name"],
                "stage_key": trigger_key,
            },
            ensure_ascii=False,
        )
        prompt = (
            "根据以下当前工程上下文，判断是否有必要主动给用户一条工程建议。\n"
            f"上下文：{proactive_context_json}\n"
            f"当前 Agent 已获准检索的本地资料：{', '.join(knowledge_files)}\n"
            "先调用 search_boundary_layer_rules 检索与该上下文相关的内容，再由你判断相关性。"
            "没有命中、内容无关或无法证明对当前阶段有帮助时，should_suggest 必须为 false。"
            "不得仅凭模板名称或阶段猜测用户的参数值。"
            "若建议成立，sources 必须逐项使用检索结果中的 source 和 section 原值。"
            "仅输出 JSON：should_suggest(bool)、relevance_reason(string)、suggestion(string)、"
            "follow_up_questions(string数组)、sources([{source,section}])。"
            "没有建议时输出 false、空 suggestion、空数组。"
        )
        async for event in agent.arun(
            prompt,
            session_id=f"{chat_session_id}:proactive",
            user_id="local-user",
            stream=True,
            stream_events=True,
            metadata={"template_id": template_id, "trigger_key": trigger_key},
        ):
            event_name = _event_name(event)
            # RunContent events carry incremental text; RunCompleted re-delivers the
            # full content, so prefer the final event when parsing the JSON output.
            if event_name == "runcontent":
                content = getattr(event, "content", None)
                if content:
                    accumulated += str(content)
            elif event_name == "runcompleted":
                complete_content = getattr(event, "content", None)
                if complete_content:
                    final_content = str(complete_content)
            if "toolcallstarted" in event_name:
                tool = getattr(event, "tool", None)
                _record_event(
                    database,
                    run_id,
                    "tool_started",
                    {
                        "tool_name": str(getattr(tool, "tool_name", "工具")),
                        "tool_args": getattr(tool, "tool_args", {}) or {},
                    },
                )
            elif "toolcallcompleted" in event_name:
                tool = getattr(event, "tool", None)
                tool_name = str(getattr(tool, "tool_name", "工具"))
                result_text = getattr(tool, "result", "")
                result_payload: object = result_text
                if isinstance(result_text, str):
                    try:
                        result_payload = json.loads(result_text)
                    except json.JSONDecodeError:
                        result_payload = result_text
                if tool_name == "search_boundary_layer_rules" and isinstance(result_payload, dict):
                    retrieved_citations.update(
                        (str(item.get("source", "")), str(item.get("section", "")))
                        for item in result_payload.get("results", [])
                        if isinstance(item, dict)
                    )
                _record_event(
                    database,
                    run_id,
                    "tool_completed",
                    {
                        "tool_name": tool_name,
                        "result": result_payload,
                    },
                )

        try:
            advice = AgentProactiveOutput.model_validate_json(
                (final_content or accumulated).strip()
            )
        except ValueError:
            advice = AgentProactiveOutput()
        citations = {(item.source, item.section) for item in advice.sources}
        if (
            not advice.should_suggest
            or not advice.suggestion.strip()
            or not retrieved_citations
            or not citations
            or not citations.issubset(retrieved_citations)
        ):
            advice = AgentProactiveOutput()
        _record_event(
            database,
            run_id,
            "relevance_assessed",
            {
                "should_suggest": advice.should_suggest,
                "relevance_reason": advice.relevance_reason,
                "sources": [citation.model_dump() for citation in advice.sources],
            },
        )
        with database.connect() as connection:
            connection.execute(
                """UPDATE agent_runs SET status = 'completed', assistant_message = ?,
                   response_json = ?, agno_run_id = ?, finished_at = ? WHERE id = ?""",
                (
                    advice.suggestion,
                    advice.model_dump_json(),
                    str(getattr(event, "run_id", "")) or None,
                    utc_now(),
                    run_id,
                ),
            )
        _record_event(database, run_id, "completed", {})
    except Exception as exc:
        with database.connect() as connection:
            connection.execute(
                """UPDATE agent_runs SET status = 'failed', error = ?, finished_at = ?
                   WHERE id = ?""",
                (str(exc)[:4_000], utc_now(), run_id),
            )
        _record_event(database, run_id, "failed", {"error": str(exc)[:2_000]})
        return None

    session = read_session(template_id, database)
    return next((item for item in session.proactive_suggestions if item.run_id == run_id), None)


@router.post("/templates/{template_id}/messages")
async def send_message(
    template_id: int,
    payload: AgentChatRequest,
    database: DatabaseDependency,
    x_model_api_key: str = Header(default=""),
) -> StreamingResponse:
    config = _get_config(database)
    if not config.enabled or config.connection_status != "passed":
        raise HTTPException(status_code=409, detail="请先在设置中测试并启用全局 AI 模型。")
    if not x_model_api_key.strip():
        raise HTTPException(status_code=409, detail="尚未安全保存全局 AI API Key。")
    agent_id, session_id = _get_template_session(database, template_id)
    template_context = _get_template_agent_context(database, template_id)
    run_id = str(uuid.uuid4())
    now = utc_now()
    try:
        with database.connect() as connection:
            duplicate = connection.execute(
                "SELECT id FROM agent_runs WHERE template_id = ? AND client_message_id = ?",
                (template_id, payload.client_message_id),
            ).fetchone()
            if duplicate:
                raise HTTPException(
                    status_code=409, detail="这条消息已提交，请从会话记录查看运行结果。"
                )
            connection.execute(
                """INSERT INTO agent_runs(id, template_id, agno_session_id, client_message_id,
                   status, user_message, created_at, model_snapshot_json)
                   VALUES (?, ?, ?, ?, 'running', ?, ?, ?)""",
                (
                    run_id,
                    template_id,
                    session_id,
                    payload.client_message_id,
                    payload.message,
                    now,
                    config.model_dump_json(),
                ),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="此模板已有 Agent 运行正在处理。") from exc

    async def event_stream() -> AsyncIterator[str]:
        accumulated = ""
        final_content = ""
        run_error = ""
        yield _sse({"type": "started", "run_id": run_id})
        try:
            _record_event(
                database,
                run_id,
                "started",
                {"confirm_out_of_range": payload.confirm_out_of_range},
            )
            if payload.images:
                _record_event(
                    database,
                    run_id,
                    "user_images",
                    {"images": [image.model_dump() for image in payload.images]},
                )
            from agno.media import Image

            images = [
                Image(
                    content=base64.b64decode(image.data_base64),
                    format=image.mime_type.removeprefix("image/"),
                    mime_type=image.mime_type,
                )
                for image in payload.images
            ]
            agent = build_agent(
                config=config.model_dump(),
                api_key=x_model_api_key,
                database_path=database.path,
                agent_id=agent_id,
                allow_out_of_range=payload.confirm_out_of_range,
                tools_enabled=config.tool_status == "passed",
                allowed_knowledge_files=template_context["knowledge_files"],
                allowed_tool_names=template_context["allowed_tools"],
            )
            async for event in agent.arun(
                payload.message,
                session_id=session_id,
                user_id="local-user",
                images=images or None,
                stream=True,
                stream_events=True,
                metadata={"template_id": template_id, "business_run_id": run_id},
            ):
                event_name = _event_name(event)
                # Agno streams incremental text via RunContent events; RunCompleted
                # re-delivers the full content and tool events carry progress strings,
                # so only RunContent deltas are forwarded and accumulated.
                if event_name == "runcontent":
                    content = getattr(event, "content", None)
                    if content:
                        text = str(content)
                        accumulated += text
                        yield _sse({"type": "content", "run_id": run_id, "content": text})
                elif event_name == "runcompleted":
                    complete_content = getattr(event, "content", None)
                    if complete_content:
                        final_content = str(complete_content)
                elif event_name == "runerror":
                    run_error = str(getattr(event, "content", "") or "模型运行出错。")
                if "toolcallstarted" in event_name:
                    tool = getattr(event, "tool", None)
                    tool_name = str(getattr(tool, "tool_name", "计算工具"))
                    tool_arguments = getattr(tool, "tool_args", {}) or {}
                    _record_event(
                        database,
                        run_id,
                        "tool_started",
                        {"tool_name": tool_name, "tool_args": tool_arguments},
                    )
                    yield _sse(
                        {
                            "type": "tool",
                            "run_id": run_id,
                            "tool_status": "running",
                            "tool_name": tool_name,
                            "content": json.dumps(tool_arguments, ensure_ascii=False),
                        }
                    )
                elif "toolcallcompleted" in event_name:
                    tool = getattr(event, "tool", None)
                    result_text = getattr(tool, "result", "")
                    tool_name = str(getattr(tool, "tool_name", "计算工具"))
                    result_payload: object = result_text
                    if isinstance(result_text, str):
                        try:
                            result_payload = json.loads(result_text)
                        except json.JSONDecodeError:
                            result_payload = result_text
                    if (
                        isinstance(result_payload, dict)
                        and result_payload.get("confirmation_required") is True
                    ):
                        _record_event(
                            database,
                            run_id,
                            "confirmation_required",
                            {"tool_name": tool_name, "result": result_payload},
                        )
                        yield _sse(
                            {
                                "type": "confirmation_required",
                                "run_id": run_id,
                                "tool_name": tool_name,
                                "content": json.dumps(result_payload, ensure_ascii=False),
                            }
                        )
                    _record_event(
                        database,
                        run_id,
                        "tool_completed",
                        {"tool_name": tool_name, "result": str(result_text or "")},
                    )
                    yield _sse(
                        {
                            "type": "tool",
                            "run_id": run_id,
                            "tool_status": "completed",
                            "tool_name": tool_name,
                            "content": str(result_text or ""),
                        }
                    )
            if run_error:
                # Agno surfaces provider errors as RunError stream events.
                with database.connect() as connection:
                    connection.execute(
                        """UPDATE agent_runs SET status = 'failed', assistant_message = ?,
                           error = ?, finished_at = ? WHERE id = ?""",
                        ("", run_error[:4_000], utc_now(), run_id),
                    )
                _record_event(database, run_id, "failed", {"error": run_error[:2_000]})
                yield _sse({"type": "error", "run_id": run_id, "content": run_error[:2_000]})
                return
            assistant_message = final_content or accumulated
            with database.connect() as connection:
                connection.execute(
                    """UPDATE agent_runs SET status = 'completed', assistant_message = ?,
                       agno_run_id = ?, finished_at = ? WHERE id = ?""",
                    (assistant_message, str(getattr(event, "run_id", "")) or None, utc_now(), run_id),
                )
            _record_event(database, run_id, "completed", {})
            yield _sse({"type": "completed", "run_id": run_id})
        except asyncio.CancelledError:
            with database.connect() as connection:
                connection.execute(
                    """UPDATE agent_runs SET status = 'interrupted', error = ?, finished_at = ?
                       WHERE id = ?""",
                    ("Agent run was stopped by the user.", utc_now(), run_id),
                )
            _record_event(database, run_id, "interrupted", {"reason": "user_stopped"})
            raise
        except Exception as exc:  # errors are persisted and surfaced to the UI
            with database.connect() as connection:
                connection.execute(
                    """UPDATE agent_runs SET status = 'failed', assistant_message = ?, error = ?,
                       finished_at = ? WHERE id = ?""",
                    (accumulated, str(exc)[:4_000], utc_now(), run_id),
                )
            _record_event(database, run_id, "failed", {"error": str(exc)[:2_000]})
            yield _sse({"type": "error", "run_id": run_id, "content": str(exc)[:2_000]})

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )
