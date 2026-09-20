import pytest

from tokenshield.metering import TokenMeter


def test_configured_pricing_and_wildcard():
    meter = TokenMeter('{"gpt-4o*": {"input_per_million": 2.5, "output_per_million": 10}}')
    assert meter.cost("gpt-4o-2024-08-06", 1_000_000, 100_000) == pytest.approx(3.5)
    assert meter.pricing_status("gpt-4o-2024-08-06") == "configured"


def test_invalid_pricing_is_rejected():
    with pytest.raises(ValueError):
        TokenMeter("not-json")


def test_unknown_model_still_has_positive_count():
    meter = TokenMeter()
    assert meter.count("hello", "unknown-model") > 0
    assert meter.pricing_status("unknown-model") == "missing"
