import json

import httpx
import pytest

from src import constants
from src.analyzers import (
    AnalysisInputSnapshot,
    DeepSeekAnalyzer,
    DeepSeekClient,
    PermanentAnalysisError,
    RetryableAnalysisError,
)
from src.analyzers.deepseek import DEEPSEEK_CHAT_COMPLETIONS_URL


MODEL = "deepseek-v4-flash"


def snapshot() -> AnalysisInputSnapshot:
    return AnalysisInputSnapshot(
        title="Synthetic payment issue",
        description="A synthetic card payment failed.",
        category=constants.Category.BILLING,
        tags=(constants.Tag.ERROR_500,),
        priority=constants.Priority.HIGH,
        status=constants.Status.OPEN,
        public_comments=("Synthetic comment.",),
    )


def response(content='{"summary":"Synthetic payment failed."}'):
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5},
    }


def make_analyzer(handler):
    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    analyzer = DeepSeekAnalyzer(
        client=DeepSeekClient(
            api_key="synthetic-deepseek-key",
            timeout_seconds=20,
            http_client=http_client,
        ),
        model=MODEL,
    )
    return analyzer, http_client


def test_deepseek_success_uses_json_object_mode_and_usage():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=response())

    analyzer, client = make_analyzer(handler)
    try:
        result = analyzer.analyze(snapshot())
    finally:
        client.close()

    assert result.summary == "Synthetic payment failed."
    assert result.input_tokens == 12
    assert result.output_tokens == 5
    assert captured["url"] == DEEPSEEK_CHAT_COMPLETIONS_URL
    assert captured["authorization"] == "Bearer synthetic-deepseek-key"
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert "\"summary\"" in captured["payload"]["messages"][0]["content"]
    assert "synthetic-deepseek-key" not in json.dumps(captured["payload"])


@pytest.mark.parametrize(
    ("status_code", "error_type", "code"),
    [
        (400, PermanentAnalysisError, "provider_bad_request"),
        (401, PermanentAnalysisError, "provider_auth_failed"),
        (402, PermanentAnalysisError, "provider_credits_exhausted"),
        (422, PermanentAnalysisError, "provider_bad_request"),
        (429, RetryableAnalysisError, "provider_rate_limited"),
        (500, RetryableAnalysisError, "provider_unavailable"),
        (503, RetryableAnalysisError, "provider_unavailable"),
    ],
)
def test_deepseek_http_errors_are_safe(status_code, error_type, code):
    analyzer, client = make_analyzer(
        lambda request: httpx.Response(
            status_code,
            json={"error": {"message": "raw synthetic body"}},
        )
    )
    try:
        with pytest.raises(error_type) as caught:
            analyzer.analyze(snapshot())
    finally:
        client.close()

    assert caught.value.code == code
    assert "raw synthetic body" not in caught.value.safe_message
