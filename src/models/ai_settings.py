from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProviderId = Literal["fake", "openrouter", "deepseek"]


class AISettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderId
    model: str = Field(min_length=1, max_length=100)
    expected_version: int = Field(ge=1)


class ProviderCapability(BaseModel):
    provider: ProviderId
    configured: bool
    configuration_status: Literal["ready", "key_missing", "unavailable"]
    selectable_models: list[str]
    default_model: str
    privacy_notice: str


class AISettingsResponse(BaseModel):
    provider: ProviderId
    model: str
    version: int
    updated_at: datetime
    updated_by_user_id: str | None
    providers: list[ProviderCapability]


class AIProviderTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderId
    model: str = Field(min_length=1, max_length=100)


class AIProviderTestResult(BaseModel):
    provider: ProviderId
    model: str
    ok: bool
    input_tokens: int | None = None
    output_tokens: int | None = None
    safe_error_code: str | None = None
