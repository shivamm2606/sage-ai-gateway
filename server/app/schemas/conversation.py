from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ConversationResponse(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageUsage(BaseModel):
    requested_model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    tokens_estimated: bool
    latency_ms: int
    first_token_ms: int | None
    routing_tier: str | None
    routing_reason: str | None

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: Literal["user", "assistant", "system"]
    content: str
    model: str | None
    status: Literal["complete", "cancelled", "error"]
    created_at: datetime
    usage: MessageUsage | None = None  # only on assistant replies

    model_config = ConfigDict(from_attributes=True)


class ConversationDetail(ConversationResponse):
    messages: list[MessageResponse]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=32_000)
    model: str | None = None  # a model id, "auto", or empty for the gateway default


class ModelResponse(BaseModel):
    id: str
    provider: str


class ModelsResponse(BaseModel):
    default: str | None
    models: list[ModelResponse]


class ModelUsage(BaseModel):
    model: str
    requests: int
    total_tokens: int
    avg_latency_ms: int


class UsageSummary(BaseModel):
    period_start: datetime
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    request_limit: int | None
    token_limit: int | None
    requests_remaining: int | None
    tokens_remaining: int | None
    by_model: list[ModelUsage]
