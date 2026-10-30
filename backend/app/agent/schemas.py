"""API contracts for the global model and template-scoped engineering agent."""

from __future__ import annotations

import base64
import binascii
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, TypeAdapter, field_validator


class AgentModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str = Field(default="", max_length=120)
    model_id: str = Field(default="", max_length=200)
    base_url: str = Field(default="", max_length=500)
    timeout_seconds: int = Field(default=90, ge=10, le=300)
    enabled: bool = False
    connection_status: Literal["untested", "passed", "failed"] = "untested"
    tool_status: Literal["untested", "passed", "failed", "unsupported"] = "untested"
    vision_status: Literal["untested", "passed", "failed", "unsupported"] = "untested"
    streaming_status: Literal["untested", "passed", "failed", "unsupported"] = "untested"

    def validate_endpoint(self) -> AgentModelConfig:
        if self.base_url:
            TypeAdapter(HttpUrl).validate_python(self.base_url)
        if self.enabled and (not self.model_id or not self.base_url):
            raise ValueError("启用模型前请填写 Model ID 和 Base URL。")
        return self


class AgentModelConfigUpdate(AgentModelConfig):
    pass


class AgentModelTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str = Field(default="", max_length=120)
    model_id: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=500)
    timeout_seconds: int = Field(default=90, ge=10, le=300)


class AgentCapabilityTestResult(BaseModel):
    tool_status: Literal["passed", "failed", "unsupported"]
    streaming_status: Literal["passed", "failed", "unsupported"]
    message: str


class AgentImageAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    filename: str = Field(min_length=1, max_length=200)
    mime_type: Literal["image/png", "image/jpeg", "image/webp"]
    data_base64: str = Field(min_length=1, max_length=6_990_508)

    @field_validator("data_base64")
    @classmethod
    def validate_image_data(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("图片数据必须是有效的 Base64 编码。") from exc
        if not decoded or len(decoded) > 5 * 1024 * 1024:
            raise ValueError("每张图片大小不能超过 5 MB。")
        return value


class AgentChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=12_000)
    client_message_id: str = Field(min_length=1, max_length=100)
    confirm_out_of_range: bool = False
    images: list[AgentImageAttachment] = Field(default_factory=list, max_length=4)


class AgentMessageRead(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    run_id: str | None = None
    status: str | None = None
    created_at: str
    attachments: list[AgentImageAttachment] = Field(default_factory=list)
    tool_name: str | None = None
    tool_status: str | None = None


class AgentProactiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    stage_key: str = Field(min_length=1, max_length=120)


class AgentKnowledgeCitation(BaseModel):
    source: str
    section: str


class AgentProactiveOutput(BaseModel):
    should_suggest: bool = False
    relevance_reason: str = ""
    suggestion: str = ""
    follow_up_questions: list[str] = Field(default_factory=list, max_length=3)
    sources: list[AgentKnowledgeCitation] = Field(default_factory=list)


class AgentProactiveSuggestionRead(AgentProactiveOutput):
    run_id: str
    stage_key: str
    execution_records: list[dict[str, object]] = Field(default_factory=list)
    created_at: str


class AgentSessionRead(BaseModel):
    template_id: int
    agent_id: str
    session_id: str
    messages: list[AgentMessageRead] = Field(default_factory=list)
    needs_range_confirmation: bool = False
    proactive_suggestions: list[AgentProactiveSuggestionRead] = Field(default_factory=list)


class AgentRunEvent(BaseModel):
    type: Literal["started", "content", "tool", "completed", "error"]
    run_id: str
    content: str = ""
    tool_name: str | None = None
    tool_status: str | None = None


class CategoryCapabilityKnowledgeRead(BaseModel):
    """Read-only knowledge source bound to a part category."""

    id: str
    name: str
    files: list[str] = Field(default_factory=list)
    status: Literal["enabled", "disabled"]
    created_at: str


class CategoryCapabilityRuleRead(BaseModel):
    """Placeholder shape for future engineering rules; V1 always returns none."""

    id: str
    name: str
    status: Literal["enabled", "disabled"] = "enabled"
    description: str = ""


class CategoryCapabilityToolRead(BaseModel):
    """Read-only approved calculation tool available to the category agent."""

    name: str
    display_name: str
    status: Literal["enabled", "disabled"] = "enabled"
    source: str = ""


class CategoryCapabilitiesRead(BaseModel):
    """Real capability inventory for one part category (Extension Workspace V1)."""

    category_id: str
    knowledge: list[CategoryCapabilityKnowledgeRead] = Field(default_factory=list)
    rules: list[CategoryCapabilityRuleRead] = Field(default_factory=list)
    tools: list[CategoryCapabilityToolRead] = Field(default_factory=list)
