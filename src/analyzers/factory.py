from dataclasses import dataclass
import re

from src.core import config

from .base import Analyzer, PermanentAnalysisError
from .fake import build_fake_analyzer
from .deepseek import DeepSeekAnalyzer, DeepSeekClient
from .openrouter import (
    OpenRouterAnalyzer,
    OpenRouterClient,
    TICKET_SUMMARY_PROMPT_VERSION,
)


FAKE_MODEL = "deterministic-fake-v1"
DEEPSEEK_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")
OPENROUTER_DEFAULT_MODEL = "openai/gpt-oss-20b"
OPENROUTER_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._:-]+$")


@dataclass(frozen=True)
class AnalyzerMetadata:
    provider: str
    model: str
    prompt_version: str


def validate_selection(provider: str, model: str) -> None:
    if provider == "fake":
        if model != FAKE_MODEL:
            raise PermanentAnalysisError(
                "invalid fake analyzer model",
                code="provider_model_invalid",
                safe_message="The selected fake model is invalid",
            )
        return
    if provider == "openrouter":
        if not OPENROUTER_MODEL_PATTERN.fullmatch(model):
            raise PermanentAnalysisError(
                "invalid OpenRouter model",
                code="provider_model_invalid",
                safe_message="The selected OpenRouter model is invalid",
            )
        return
    if provider == "deepseek":
        if model not in DEEPSEEK_MODELS:
            raise PermanentAnalysisError(
                "invalid DeepSeek model",
                code="provider_model_invalid",
                safe_message="The selected DeepSeek model is invalid",
            )
        return
    raise PermanentAnalysisError(
        "unsupported analyzer provider",
        code="provider_config_error",
        safe_message="Analyzer provider configuration is invalid",
    )


def configured_analyzer_metadata(
    *,
    provider: str | None = None,
    model: str | None = None,
) -> AnalyzerMetadata:
    provider = provider or config.ANALYZER_PROVIDER
    if provider == "fake":
        selected_model = model or FAKE_MODEL
    elif provider == "openrouter":
        selected_model = model or config.OPENROUTER_MODEL
    elif provider == "deepseek":
        selected_model = model or DEEPSEEK_MODELS[0]
    else:
        raise PermanentAnalysisError(
            "unsupported analyzer provider",
            code="provider_config_error",
            safe_message="Analyzer provider configuration is invalid",
        )
    validate_selection(provider, selected_model)
    return AnalyzerMetadata(
        provider=provider,
        model=selected_model,
        prompt_version=TICKET_SUMMARY_PROMPT_VERSION,
    )


def build_analyzer(
    *,
    provider: str,
    model: str,
    prompt_version: str,
) -> Analyzer:
    validate_selection(provider, model)
    if provider == "fake":
        if prompt_version != TICKET_SUMMARY_PROMPT_VERSION:
            raise PermanentAnalysisError(
                "invalid fake analyzer metadata",
                code="provider_config_error",
                safe_message="Analyzer provider configuration is invalid",
            )
        return build_fake_analyzer()
    if provider == "openrouter":
        if not config.OPENROUTER_API_KEY or not config.OPENROUTER_API_KEY.strip():
            raise PermanentAnalysisError(
                "invalid OpenRouter configuration",
                code="provider_config_error",
                safe_message="OpenRouter configuration is invalid",
            )
        if config.OPENROUTER_TIMEOUT_SECONDS <= 0:
            raise PermanentAnalysisError(
                "invalid OpenRouter timeout",
                code="provider_config_error",
                safe_message="OpenRouter configuration is invalid",
            )
        return OpenRouterAnalyzer(
            client=OpenRouterClient(
                api_key=config.OPENROUTER_API_KEY or "",
                timeout_seconds=config.OPENROUTER_TIMEOUT_SECONDS,
            ),
            model=model,
            prompt_version=prompt_version,
        )
    if provider == "deepseek":
        if not config.DEEPSEEK_API_KEY or not config.DEEPSEEK_API_KEY.strip():
            raise PermanentAnalysisError(
                "invalid DeepSeek configuration",
                code="provider_config_error",
                safe_message="DeepSeek configuration is invalid",
            )
        if config.DEEPSEEK_TIMEOUT_SECONDS <= 0:
            raise PermanentAnalysisError(
                "invalid DeepSeek timeout",
                code="provider_config_error",
                safe_message="DeepSeek configuration is invalid",
            )
        return DeepSeekAnalyzer(
            client=DeepSeekClient(
                api_key=config.DEEPSEEK_API_KEY,
                timeout_seconds=config.DEEPSEEK_TIMEOUT_SECONDS,
            ),
            model=model,
            prompt_version=prompt_version,
        )
    raise PermanentAnalysisError(
        "unsupported analyzer provider",
        code="provider_config_error",
        safe_message="Analyzer provider configuration is invalid",
    )
