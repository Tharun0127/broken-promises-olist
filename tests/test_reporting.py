"""Tests for the template renderer and the hand-typed-number check."""
import pytest

from src import report, verify


def test_render_formats():
    m = {"a": 0.1234, "b": -0.017, "c": 12345.6, "d": 2553.9}
    out = report.render("{{a|pct}} {{b|pp}} {{c|int}} {{d|brl}}", m)
    assert out == "12.3% -1.7 pp 12,346 R$ 2,554"


def test_render_fails_on_unknown_metric():
    with pytest.raises(KeyError):
        report.render("{{missing|pct}}", {})


def test_number_check_accepts_rendered_metrics_and_rejects_typed_numbers():
    m = {"late_rate": 0.0677, "orders": 99441}
    cands = verify.candidates(m)
    good = report.render("Late rate {{late_rate|pct}} of {{orders|int}} orders, 180 days, 1-star.", m)
    assert verify.untraced_numbers(good, cands)[0] == []
    bad = good + " About 42.0% were reviewed."
    assert verify.untraced_numbers(bad, cands)[0] == ["42.0"]


def test_number_check_ignores_code_and_file_names():
    text = "See `sql/marts/02_mart.sql` and\n```\npython run_all.py --seed 77\n```\n[a](docs/x2.md)"
    assert verify.untraced_numbers(text, set())[0] == []


def test_trailing_comma_is_not_part_of_a_number():
    assert verify.NUM.findall("day 1, then 1,245 orders") == ["1", "1,245"]
