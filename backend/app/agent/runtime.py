"""Agno runtime construction for the local engineering assistant."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agent.retrieval import SOURCE_FILES
from app.agent.tools import create_tools

GENERAL_INSTRUCTIONS = (
    "你是 Fluent Meshing 模板编辑器中的工程辅助 Agent。请用简洁中文回答。\n"
    "回复使用简洁 Markdown（加粗、列表、行内代码），不要在回复中原样粘贴工具返回的 JSON 或原始检索文本，"
    "只提炼与用户问题相关的结论、数值和依据。\n"
    "先核对用户已给的数据，每次只询问最影响判断的缺项。\n"
    "区分用户输入、工程假设、知识依据和确定性工具结果。\n"
    "只有用户要求联网或问题涉及当前外部信息时才调用 web_search；项目算法规则以本地检索结果为准。\n"
    "引用联网结果时给出结果中的来源网址；网络结果不能替代项目本地规则。\n"
    "数值建议只能通过已注册工具计算，不得编造工具调用或结果。\n"
    "不要修改 Fluent 表单、CAD 文件或启动 Fluent 操作，用户手工填写建议。\n"
    "Smooth Transition 工具只计算层数，需要首层 y+、外层 y+ 和增长率。\n"
    "Uniform 工具只计算 First Height，需要密度、动力黏度、特征速度、特征直径和首层 y+。\n"
    "Uniform 不推算喉部速度或层数。\n"
    "说明算法假设、Fluent 字段映射状态和求解后的 Wall Yplus 验证。"
)

BOUNDARY_LAYER_INSTRUCTIONS = (
    "结合用户提供的工况与图片比较 Uniform 和 Smooth Transition，\n"
    "说明推荐理由并保留用户选择权。Smooth 需要首层 y+、外层 y+ 和增长率。\n"
    "Uniform 需要密度、动力黏度、用户提供的特征速度、特征直径和首层 y+。\n"
    "不得要求或估算喉部速度。明确且带单位的文字值可直接使用；模糊值、图片识别值和假设需确认。"
)


def build_agent(
    *,
    config: dict[str, Any],
    api_key: str,
    database_path: Path,
    agent_id: str,
    allow_out_of_range: bool = False,
    tools_enabled: bool = True,
    allowed_knowledge_files: tuple[str, ...] = SOURCE_FILES,
    allowed_tool_names: tuple[str, ...] = (
        "calculate_smooth_layers",
        "calculate_uniform_first_height",
    ),
) -> Any:
    """Build the mandatory Agno Agent using one global OpenAI-compatible model profile."""
    from agno.agent import Agent
    from agno.db.sqlite import SqliteDb
    from agno.models.openai.like import OpenAILike

    model = OpenAILike(
        id=str(config["model_id"]),
        name=str(config.get("display_name") or config["model_id"]),
        base_url=str(config["base_url"]),
        api_key=api_key,
        timeout=float(config.get("timeout_seconds", 90)),
        max_retries=0,
    )
    instructions = GENERAL_INSTRUCTIONS
    if allowed_knowledge_files:
        instructions = (
            f"{instructions}\n\n{BOUNDARY_LAYER_INSTRUCTIONS}\n"
            "回答本地专业规则前先调用 search_boundary_layer_rules，并标注来源文件和章节。"
        )
    else:
        instructions = (
            f"{instructions}\n\n当前模板未关联本地专业知识库。"
            "明确说明缺少项目资料依据，不得声称已检索或引用项目规则。"
        )
    if not tools_enabled:
        instructions = (
            f"{instructions}\n\n当前模型尚未通过工具调用能力测试。"
            "可以解释方法和询问参数，但不得提供确定性数值计算结果。"
        )
    registered_tools = (
        create_tools(
            allow_out_of_range=allow_out_of_range,
            allowed_knowledge_files=allowed_knowledge_files,
            allowed_tool_names=allowed_tool_names,
        )
        if tools_enabled
        else []
    )
    return Agent(
        id=agent_id,
        name="Fluent Engineering Assistant",
        model=model,
        db=SqliteDb(db_file=str(database_path)),
        tools=registered_tools,
        instructions=instructions,
        add_history_to_context=True,
        num_history_runs=12,
        telemetry=False,
    )
