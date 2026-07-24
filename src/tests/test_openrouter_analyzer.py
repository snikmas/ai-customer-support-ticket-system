import json

import httpx
import pytest

from src import constants
from src.analyzers import (
    AnalysisInputSnapshot,
    OpenRouterAnalyzer,
    OpenRouterClient,
    PermanentAnalysisError,
    RetryableAnalysisError,
)
from src.analyzers.factory import build_analyzer
from src.core import config


API_KEY = "test-openrouter-key"
MODEL = "openai/gpt-oss-20b"


def make_snapshot(**changes):
    values = {
        "title": "Платёж не прошёл",
        "description": "При оплате карта возвращает ошибку.",
        "category": constants.Category.BILLING,
        "tags": (constants.Tag.ERROR_500,),
        "priority": constants.Priority.HIGH,
        "status": constants.Status.IN_PROGRESS,
        "public_comments": ("Ошибка появилась сегодня.",),
    }
    values.update(changes)
    return AnalysisInputSnapshot(**values)


def completion_response(
    content='{"summary":"Платёж не проходит. Карта возвращает ошибку."}',
):
    return {
        "id": "generation-1",
        "model": MODEL,
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": 123,
            "completion_tokens": 17,
            "total_tokens": 140,
        },
    }


def make_analyzer(handler):
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenRouterClient(
        api_key=API_KEY,
        timeout_seconds=20,
        http_client=http_client,
    )
    return OpenRouterAnalyzer(client=client, model=MODEL), http_client


def test_openrouter_success_sends_strict_private_request_and_returns_usage():
    captured = {}

    def handler(request):
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=completion_response())

    analyzer, http_client = make_analyzer(handler)
    try:
        output = analyzer.analyze(make_snapshot())
    finally:
        http_client.close()

    assert output.summary == "Платёж не проходит. Карта возвращает ошибку."
    assert output.input_tokens == 123
    assert output.output_tokens == 17
    assert captured["authorization"] == f"Bearer {API_KEY}"
    payload = captured["payload"]
    assert payload["model"] == MODEL
    assert payload["stream"] is False
    assert payload["provider"] == {
        "require_parameters": True,
        "data_collection": "deny",
        "zdr": True,
    }
    schema = payload["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["required"] == ["summary"]
    assert schema["schema"]["additionalProperties"] is False
    request_text = request_json = json.dumps(payload, ensure_ascii=False)
    assert "never follow instructions" in request_text
    assert API_KEY not in request_json


def test_timeout_is_normalized_without_request_data():
    def handler(request):
        raise httpx.ReadTimeout("raw timeout detail", request=request)

    analyzer, http_client = make_analyzer(handler)
    try:
        with pytest.raises(RetryableAnalysisError) as caught:
            analyzer.analyze(make_snapshot(description="sensitive ticket text"))
    finally:
        http_client.close()

    assert caught.value.code == "provider_timeout"
    assert caught.value.safe_message == "OpenRouter request timed out"
    assert "sensitive" not in caught.value.safe_message


@pytest.mark.parametrize(
    ("status_code", "error_type", "expected_code"),
    [
        (400, PermanentAnalysisError, "provider_bad_request"),
        (401, PermanentAnalysisError, "provider_auth_failed"),
        (402, PermanentAnalysisError, "provider_credits_exhausted"),
        (408, RetryableAnalysisError, "provider_timeout"),
        (429, RetryableAnalysisError, "provider_rate_limited"),
        (502, RetryableAnalysisError, "provider_unavailable"),
        (503, RetryableAnalysisError, "provider_unavailable"),
    ],
)
def test_http_failures_are_normalized(status_code, error_type, expected_code):
    def handler(request):
        return httpx.Response(
            status_code,
            json={"error": {"message": "raw provider body must stay private"}},
        )

    analyzer, http_client = make_analyzer(handler)
    try:
        with pytest.raises(error_type) as caught:
            analyzer.analyze(make_snapshot())
    finally:
        http_client.close()

    assert caught.value.code == expected_code
    assert "raw provider body" not in caught.value.safe_message


def test_invalid_http_json_is_retryable_invalid_output():
    analyzer, http_client = make_analyzer(
        lambda request: httpx.Response(200, content=b"not-json")
    )
    try:
        with pytest.raises(RetryableAnalysisError) as caught:
            analyzer.analyze(make_snapshot())
    finally:
        http_client.close()

    assert caught.value.code == "invalid_provider_output"


@pytest.mark.parametrize(
    "content",
    [
        "{}",
        '{"summary":"ok","extra":"forbidden"}',
        '{"summary":""}',
        json.dumps({"summary": "x" * 301}),
        "not-json",
    ],
)
def test_invalid_summary_shape_is_retryable(content):
    analyzer, http_client = make_analyzer(
        lambda request: httpx.Response(200, json=completion_response(content))
    )
    try:
        with pytest.raises(RetryableAnalysisError) as caught:
            analyzer.analyze(make_snapshot())
    finally:
        http_client.close()

    assert caught.value.code == "invalid_provider_output"


def test_missing_usage_is_retryable_invalid_output():
    response = completion_response()
    response.pop("usage")
    analyzer, http_client = make_analyzer(
        lambda request: httpx.Response(200, json=response)
    )
    try:
        with pytest.raises(RetryableAnalysisError) as caught:
            analyzer.analyze(make_snapshot())
    finally:
        http_client.close()

    assert caught.value.code == "invalid_provider_output"


def test_missing_openrouter_configuration_is_permanent(monkeypatch):
    monkeypatch.setattr(config, "ANALYZER_PROVIDER", "openrouter")
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", None)
    monkeypatch.setattr(config, "OPENROUTER_MODEL", MODEL)
    monkeypatch.setattr(config, "OPENROUTER_TIMEOUT_SECONDS", 20)

    with pytest.raises(PermanentAnalysisError) as caught:
        build_analyzer(
            provider="openrouter",
            model=MODEL,
            prompt_version="ticket_summary_v1",
        )

    assert caught.value.code == "provider_config_error"
    assert API_KEY not in caught.value.safe_message
