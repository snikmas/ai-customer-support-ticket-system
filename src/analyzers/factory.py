from dataclasses import dataclass

from src.core import config

from .base import Analyzer, PermanentAnalysisError
from .fake import build_fake_analyzer
from .openrouter import (
    OpenRouterAnalyzer,
    OpenRouterClient,
    TICKET_SUMMARY_PROMPT_VERSION,
)


FAKE_MODEL = "deterministic-fake-v1"


@dataclass(frozen=True)
class AnalyzerMetadata:
    provider: str
    model: str
    prompt_version: str


def configured_analyzer_metadata() -> AnalyzerMetadata:
    provider = config.ANALYZER_PROVIDER
    if provider == "fake":
        return AnalyzerMetadata(
            provider="fake",
            model=FAKE_MODEL,
            prompt_version=TICKET_SUMMARY_PROMPT_VERSION,
        )
    if provider == "openrouter":
        if not config.OPENROUTER_MODEL:
            raise PermanentAnalysisError(
                "missing OpenRouter model",
                code="provider_config_error",
                safe_message="OpenRouter configuration is invalid",
            )
        return AnalyzerMetadata(
            provider="openrouter",
            model=config.OPENROUTER_MODEL,
            prompt_version=TICKET_SUMMARY_PROMPT_VERSION,
        )
    raise PermanentAnalysisError(
        "unsupported analyzer provider",
        code="provider_config_error",
        safe_message="Analyzer provider configuration is invalid",
    )


def build_analyzer(
    *,
    provider: str,
    model: str,
    prompt_version: str,
) -> Analyzer:
    if config.ANALYZER_PROVIDER != provider:
        raise PermanentAnalysisError(
            "worker analyzer provider does not match reserved provider",
            code="provider_config_error",
            safe_message="Analyzer provider configuration is invalid",
        )
    if provider == "fake":
        if model != FAKE_MODEL or prompt_version != TICKET_SUMMARY_PROMPT_VERSION:
            raise PermanentAnalysisError(
                "invalid fake analyzer metadata",
                code="provider_config_error",
                safe_message="Analyzer provider configuration is invalid",
            )
        return build_fake_analyzer()
    if provider == "openrouter":
        try:
            config.validate_analyzer_settings()
        except RuntimeError as exc:
            raise PermanentAnalysisError(
                "invalid OpenRouter configuration",
                code="provider_config_error",
                safe_message="OpenRouter configuration is invalid",
            ) from exc
        return OpenRouterAnalyzer(
            client=OpenRouterClient(
                api_key=config.OPENROUTER_API_KEY or "",
                timeout_seconds=config.OPENROUTER_TIMEOUT_SECONDS,
            ),
            model=model,
            prompt_version=prompt_version,
        )
    raise PermanentAnalysisError(
        "unsupported analyzer provider",
        code="provider_config_error",
        safe_message="Analyzer provider configuration is invalid",
    )
