from src import constants
from src import models as api_models
from src.analyzers import (
    AnalysisInputSnapshot,
    PermanentAnalysisError,
    RetryableAnalysisError,
    build_analyzer,
    configured_analyzer_metadata,
    validate_selection,
)
from src.analyzers.factory import DEEPSEEK_MODELS, FAKE_MODEL, OPENROUTER_DEFAULT_MODEL
from src.core import config
from src.db import operations
from src.exceptions import AuthorizationError, BadRequestError, ConflictError


ADMIN_ROLES = {constants.Role.ADMIN, constants.Role.SUPER_ADMIN}


def _authorize(requester: api_models.User) -> None:
    if requester.role not in ADMIN_ROLES:
        raise AuthorizationError(
            "Only administrators can manage AI settings",
            code="ai_settings_forbidden",
        )


def _provider_capabilities() -> list[api_models.ProviderCapability]:
    return [
        api_models.ProviderCapability(
            provider="fake",
            configured=True,
            configuration_status="ready",
            selectable_models=[FAKE_MODEL],
            default_model=FAKE_MODEL,
            privacy_notice="Runs locally with deterministic synthetic output.",
        ),
        api_models.ProviderCapability(
            provider="openrouter",
            configured=bool(config.OPENROUTER_API_KEY and config.OPENROUTER_API_KEY.strip()),
            configuration_status=(
                "ready"
                if config.OPENROUTER_API_KEY and config.OPENROUTER_API_KEY.strip()
                else "key_missing"
            ),
            selectable_models=[config.OPENROUTER_MODEL or OPENROUTER_DEFAULT_MODEL],
            default_model=config.OPENROUTER_MODEL or OPENROUTER_DEFAULT_MODEL,
            privacy_notice="Uses OpenRouter with the adapter's data-collection denial and ZDR controls.",
        ),
        api_models.ProviderCapability(
            provider="deepseek",
            configured=bool(config.DEEPSEEK_API_KEY and config.DEEPSEEK_API_KEY.strip()),
            configuration_status=(
                "ready"
                if config.DEEPSEEK_API_KEY and config.DEEPSEEK_API_KEY.strip()
                else "key_missing"
            ),
            selectable_models=list(DEEPSEEK_MODELS),
            default_model=DEEPSEEK_MODELS[0],
            privacy_notice="Direct DeepSeek is external; use synthetic data. ResolveAI does not claim request-level ZDR equivalence.",
        ),
    ]


def _response(setting) -> api_models.AISettingsResponse:
    return api_models.AISettingsResponse(
        provider=setting.provider,
        model=setting.model,
        version=setting.version,
        updated_at=setting.updated_at,
        updated_by_user_id=setting.updated_by_user_id,
        providers=_provider_capabilities(),
    )


def get_settings(requester: api_models.User) -> api_models.AISettingsResponse:
    _authorize(requester)
    return _response(operations.get_ai_setting())


def update_settings(
    data: api_models.AISettingsUpdate,
    requester: api_models.User,
) -> api_models.AISettingsResponse:
    _authorize(requester)
    try:
        validate_selection(data.provider, data.model)
    except PermanentAnalysisError as exc:
        raise BadRequestError(exc.safe_message, code=exc.code) from exc

    updated = operations.update_ai_setting(
        provider=data.provider,
        model=data.model,
        expected_version=data.expected_version,
        updated_by_user_id=requester.id,
        now=constants.utc_now(),
    )
    if updated is None:
        raise ConflictError(
            "AI settings changed; reload before saving",
            code="ai_settings_conflict",
        )
    return _response(updated)


def _synthetic_snapshot() -> AnalysisInputSnapshot:
    return AnalysisInputSnapshot(
        title="Synthetic ResolveAI verification ticket",
        description="Synthetic data only: verify the summary adapter path.",
        category=constants.Category.DOCUMENTATION,
        tags=(constants.Tag.PYTHON,),
        priority=constants.Priority.NORMAL,
        status=constants.Status.OPEN,
        public_comments=("Synthetic comment for provider verification.",),
    )


def test_provider(
    data: api_models.AIProviderTestRequest,
    requester: api_models.User,
) -> api_models.AIProviderTestResult:
    _authorize(requester)
    safe_error_code = None
    try:
        validate_selection(data.provider, data.model)
        metadata = configured_analyzer_metadata(
            provider=data.provider,
            model=data.model,
        )
        output = build_analyzer(
            provider=metadata.provider,
            model=metadata.model,
            prompt_version=metadata.prompt_version,
        ).analyze(_synthetic_snapshot())
        result = api_models.AIProviderTestResult(
            provider=data.provider,
            model=data.model,
            ok=True,
            input_tokens=output.input_tokens,
            output_tokens=output.output_tokens,
        )
    except RetryableAnalysisError as exc:
        safe_error_code = exc.code
        result = api_models.AIProviderTestResult(
            provider=data.provider,
            model=data.model,
            ok=False,
            safe_error_code=safe_error_code,
        )
    except PermanentAnalysisError as exc:
        safe_error_code = exc.code
        result = api_models.AIProviderTestResult(
            provider=data.provider,
            model=data.model,
            ok=False,
            safe_error_code=safe_error_code,
        )
    except Exception:
        safe_error_code = "provider_unavailable"
        result = api_models.AIProviderTestResult(
            provider=data.provider,
            model=data.model,
            ok=False,
            safe_error_code=safe_error_code,
        )
    finally:
        operations.record_ai_provider_test(
            provider=data.provider,
            model=data.model,
            actor_user_id=requester.id,
            ok=safe_error_code is None,
            error_code=safe_error_code,
            now=constants.utc_now(),
        )
    return result
