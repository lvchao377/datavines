from datetime import datetime
from decimal import Decimal

import pytest

from app.metrics.judge import compare, compute_expected, formula_result, judge, score_of


def test_count_formula_and_operators():
    assert formula_result("count", 3, 0) == Decimal("3")
    assert compare(3, "eq", 3) is True
    assert compare(3, "lt", 3) is False
    assert compare(3, "lte", 3) is True
    assert compare(4, "gt", 3) is True
    assert compare(3, "gte", 3) is True
    assert compare(3, "neq", 4) is True
    passed = judge(0, 0, "count", "eq", 0, "NEGATIVE")
    assert passed.success is True and passed.state == 1 and passed.score == Decimal("100")
    failed = judge(2, 0, "count", "eq", 0, "NEGATIVE")
    assert failed.success is False and failed.state == 2 and failed.score == Decimal("0")


def test_diff_and_percentage_match_upstream_scale():
    assert formula_result("diff", 10, 7) == Decimal("3")
    assert formula_result("diff-actual-expected", 10, 7) == Decimal("3")
    # 1/3 quantized to 4 places then * 100 => 33.3300
    assert formula_result("percentage", 1, 3) == Decimal("33.3300")
    assert formula_result("diff-percentage", 10, 8) == Decimal("25.0000")
    assert formula_result("percentage", 1, 0) == Decimal("0")
    assert formula_result("diff-percentage", 5, 0) == Decimal("0")
    neg = score_of("percentage", 1, 4, True, "NEGATIVE")
    assert neg == Decimal("100") - Decimal("25.0000")
    pos = score_of("percentage", 1, 4, True, "POSITIVE")
    assert pos == Decimal("25.0000")
    # diff-percentage score is the percentage itself, success or not
    assert score_of("diff-percentage", 10, 8, False, "POSITIVE") == Decimal("25.0000")


def test_expected_windows_round_half_up():
    moment = datetime(2026, 10, 30, 15, 0, 0)
    history = [
        (datetime(2026, 10, 30, 1, 0, 0), Decimal("10")),
        (datetime(2026, 10, 30, 2, 0, 0), Decimal("20")),
        (datetime(2026, 10, 29, 12, 0, 0), Decimal("100")),
        (datetime(2026, 10, 1, 0, 0, 0), Decimal("4")),
        (datetime(2026, 9, 30, 0, 0, 0), Decimal("999")),
    ]
    assert compute_expected("none") == Decimal("0")
    assert compute_expected("fix_value", fix_value="1.5") == Decimal("1.5")
    assert compute_expected("daily_avg", history=history, data_time=moment) == Decimal("15.00")
    assert compute_expected("last_7_day_avg", history=history, data_time=moment) == Decimal("43.33")
    assert compute_expected("weekly_avg", history=history, data_time=moment) == Decimal("43.33")
    assert compute_expected("monthly_avg", history=history, data_time=moment) == Decimal("33.50")
    # 30-day window starts on 2026-09-30 and therefore includes 999.
    assert compute_expected("last_30_day_avg", history=history, data_time=moment) == Decimal("226.60")
    assert compute_expected("table_total_rows", table_rows=8) == Decimal("8")
    assert compute_expected("target_table_total_rows", target_table_rows=3) == Decimal("3")
    assert compute_expected("daily_avg", history=[], data_time=moment) == Decimal("0")
    with pytest.raises(ValueError):
        compute_expected("fix_value")
