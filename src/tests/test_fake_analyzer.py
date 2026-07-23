import pytest
from pydantic import ValidationError

from src import constants
from src.analyzers import (
    AnalysisInputSnapshot,
    DeterministicFakeAnalyzer,
    PermanentAnalysisError,
    RetryableAnalysisError,
    build_fake_analyzer,
)


def make_snapshot(**changes):
    values = {
        "title": "  Payment   failed ",
        "description": " Card payment\nreturns   error 500. ",
        "category": constants.Category.BILLING,
        "tags": (constants.Tag.ERROR_500,),
        "priority": constants.Priority.HIGH,
        "status": constants.Status.IN_PROGRESS,
    }
    values.update(changes)
    return AnalysisInputSnapshot(**values)


def test_fake_analyzer_returns_exact_deterministic_summary():
    analyzer = DeterministicFakeAnalyzer()
    snapshot = make_snapshot()

    first = analyzer.analyze(snapshot)
    second = analyzer.analyze(snapshot)

    assert first == second
    assert first.summary == "Payment failed: Card payment returns error 500."


def test_fake_analyzer_truncates_at_word_boundary_to_valid_output():
    snapshot = make_snapshot(
        title="Long report",
        description=" ".join(["failure"] * 100),
    )

    output = DeterministicFakeAnalyzer().analyze(snapshot)

    assert len(output.summary) <= 300
    assert output.summary.endswith("...")
    assert not output.summary.endswith("fail...")


def test_snapshot_and_output_are_immutable():
    snapshot = make_snapshot()
    output = DeterministicFakeAnalyzer().analyze(snapshot)

    with pytest.raises(ValidationError):
        snapshot.title = "changed"
    with pytest.raises(ValidationError):
        output.summary = "changed"


def test_fake_analyzer_rejects_unbounded_delay():
    with pytest.raises(ValueError, match="between 0 and 10"):
        DeterministicFakeAnalyzer(delay_seconds=11)


def test_fake_analyzer_uses_controlled_delay_without_real_sleep():
    delays = []
    analyzer = DeterministicFakeAnalyzer(delay_seconds=3, sleeper=delays.append)

    analyzer.analyze(make_snapshot())

    assert delays == [3]


@pytest.mark.parametrize(
    ("failure_mode", "error_type"),
    [
        ("retryable", RetryableAnalysisError),
        ("permanent", PermanentAnalysisError),
    ],
)
def test_fake_analyzer_supports_controlled_failures(failure_mode, error_type):
    analyzer = DeterministicFakeAnalyzer(failure_mode=failure_mode)

    with pytest.raises(error_type):
        analyzer.analyze(make_snapshot())


def test_fake_analyzer_environment_controls_are_bounded(monkeypatch):
    monkeypatch.setenv("FAKE_ANALYZER_DELAY_SECONDS", "2")
    monkeypatch.setenv("FAKE_ANALYZER_FAILURE_MODE", "permanent")

    analyzer = build_fake_analyzer()

    with pytest.raises(PermanentAnalysisError):
        analyzer.analyze(make_snapshot())


def test_analyzer_modules_do_not_import_database_or_redis():
    import src.analyzers.base as base_module
    import src.analyzers.fake as fake_module

    names = set(base_module.__dict__) | set(fake_module.__dict__)
    assert "redis" not in names
    assert "operations" not in names
    assert "Session" not in names
