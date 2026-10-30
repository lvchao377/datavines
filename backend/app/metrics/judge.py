"""Result formulas, operators and expected-value windows.

Formula math follows the upstream plugins:

- count: result = actual; score = 100 if success else 0
- diff: result = |actual - expected|; score = 100 / 0
- diff-actual-expected: result = actual - expected; score = 100 / 0
- percentage: result = actual/expected*100 (scale 4 half up on the division);
  score = result when direction is POSITIVE, else 100 - result
- diff-percentage: result = |actual-expected|/expected*100; score = result
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

FORMULAS = [
    {"label": "实际值", "value": "count", "name": "Actual", "symbol": "#", "type": "value"},
    {"label": "|实际值-期望值|", "value": "diff", "name": "|Actual-Expected|", "symbol": "Δ", "type": "value"},
    {"label": "实际值-期望值", "value": "diff-actual-expected", "name": "Actual-Expected", "symbol": "Δ", "type": "value"},
    {"label": "实际值/期望值*100%", "value": "percentage", "name": "Actual/Expected*100%", "symbol": "%", "type": "percentage"},
    {"label": "|实际值-期望值|/期望值*100%", "value": "diff-percentage", "name": "|Actual-Expected|/Expected*100%", "symbol": "Δ%", "type": "percentage"},
]

OPERATORS = [
    {"label": "=", "value": "eq", "symbol": "="},
    {"label": "<", "value": "lt", "symbol": "<"},
    {"label": "<=", "value": "lte", "symbol": "<="},
    {"label": ">", "value": "gt", "symbol": ">"},
    {"label": ">=", "value": "gte", "symbol": ">="},
    {"label": "!=", "value": "neq", "symbol": "!="},
]

EXPECTED_TYPES = [
    {"label": "无", "value": "none", "needs_fix": False, "scope": "all"},
    {"label": "固定值", "value": "fix_value", "needs_fix": True, "scope": "all"},
    {"label": "日均值", "value": "daily_avg", "needs_fix": False, "scope": "all"},
    {"label": "周均值", "value": "weekly_avg", "needs_fix": False, "scope": "all"},
    {"label": "月均值", "value": "monthly_avg", "needs_fix": False, "scope": "all"},
    {"label": "最近7天均值", "value": "last_7_day_avg", "needs_fix": False, "scope": "all"},
    {"label": "最近30天均值", "value": "last_30_day_avg", "needs_fix": False, "scope": "all"},
    {"label": "表总行数", "value": "table_total_rows", "needs_fix": False, "scope": "all"},
    {"label": "目标表总行数", "value": "target_table_total_rows", "needs_fix": False, "scope": "reconciliation"},
]

_OPS = {item["value"]: item["symbol"] for item in OPERATORS}


def _d(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def formula_result(formula: str, actual, expected) -> Decimal:
    actual_d = _d(actual)
    expected_d = _d(expected)
    name = (formula or "count").strip()
    if name == "count":
        return actual_d
    if name == "diff":
        return abs(actual_d - expected_d)
    if name == "diff-actual-expected":
        return actual_d - expected_d
    if name == "percentage":
        if expected_d == 0:
            return Decimal("0")
        return _q4(actual_d / expected_d) * Decimal("100")
    if name == "diff-percentage":
        if expected_d == 0:
            return Decimal("0")
        return _q4(abs(actual_d - expected_d) / expected_d) * Decimal("100")
    raise KeyError(f"未知结果公式: {formula}")


def compare(result, operator: str, threshold) -> bool:
    op = (operator or "eq").strip()
    if op not in _OPS and op not in {item["symbol"] for item in OPERATORS}:
        # accept symbol form
        symbol_to_code = {item["symbol"]: item["value"] for item in OPERATORS}
        if op in symbol_to_code:
            op = symbol_to_code[op]
        else:
            raise KeyError(f"未知比较符: {operator}")
    left = _d(result)
    right = _d(threshold)
    if op == "eq":
        return left == right
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "neq":
        return left != right
    raise KeyError(operator)


def score_of(formula: str, actual, expected, success: bool, direction: str) -> Decimal:
    name = (formula or "count").strip()
    if name in ("count", "diff", "diff-actual-expected"):
        return Decimal("100") if success else Decimal("0")
    if name == "diff-percentage":
        return formula_result(name, actual, expected)
    if name == "percentage":
        expected_d = _d(expected)
        if expected_d == 0:
            return Decimal("0")
        ratio = _q4(_d(actual) / expected_d) * Decimal("100")
        if (direction or "POSITIVE").upper() == "NEGATIVE":
            return Decimal("100") - ratio
        return ratio
    raise KeyError(formula)


@dataclass
class Judgment:
    actual: Decimal
    expected: Decimal
    result: Decimal
    success: bool
    score: Decimal
    state: int
    formula: str
    operator: str
    threshold: Decimal

    def as_dict(self) -> dict:
        return {
            "actualValue": float(_q4(self.actual)) if self.actual == self.actual.to_integral_value() or True else float(self.actual),
            "expectedValue": float(self.expected),
            "formulaResult": float(self.result),
            "success": self.success,
            "score": float(self.score),
            "state": self.state,
            "resultFormula": self.formula,
            "operator": self.operator,
            "threshold": float(self.threshold),
        }


def judge(actual, expected, formula: str, operator: str, threshold, direction: str = "POSITIVE") -> Judgment:
    actual_d = _d(actual)
    expected_d = _d(expected)
    threshold_d = _d(threshold)
    result = formula_result(formula, actual_d, expected_d)
    # Compare using the same scale the engine stores (4 decimal places) for value formulas
    # that are not already scaled inside the formula. Keep percentage results as produced.
    stored_result = result if (formula or "count") in ("percentage", "diff-percentage") else result
    success = compare(stored_result, operator, threshold_d)
    score = score_of(formula, actual_d, expected_d, success, direction)
    return Judgment(
        actual=actual_d,
        expected=expected_d,
        result=stored_result,
        success=success,
        score=score,
        state=1 if success else 2,
        formula=(formula or "count"),
        operator=operator,
        threshold=threshold_d,
    )


def compute_expected(kind: str, *, fix_value=None, history: list[tuple[datetime, Decimal]] | None = None, data_time: datetime | None = None, table_rows=None, target_table_rows=None) -> Decimal:
    """Compute an expected value.

    history rows are (data_time, actual_value) already recorded for the same unique_code.
    Windows match the upstream MySQL templates (day bounds are half-open [start, next_day)).
    Averages are rounded to 2 decimal places. An empty window yields 0.
    """
    name = (kind or "none").strip()
    if name in ("none", ""):
        return Decimal("0")
    if name == "fix_value":
        if fix_value is None or str(fix_value) == "":
            raise ValueError("固定值期望需要 expected_value")
        return _d(fix_value)
    if name == "table_total_rows":
        return _d(table_rows if table_rows is not None else 0)
    if name == "target_table_total_rows":
        return _d(target_table_rows if target_table_rows is not None else 0)
    if name not in ("daily_avg", "weekly_avg", "monthly_avg", "last_7_day_avg", "last_30_day_avg"):
        raise KeyError(f"未知期望值类型: {kind}")

    moment = data_time or datetime.now()
    start_of_day = datetime(moment.year, moment.month, moment.day)
    next_day = start_of_day + timedelta(days=1)
    if name == "daily_avg":
        start = start_of_day
    elif name == "last_7_day_avg":
        start = start_of_day - timedelta(days=7)
    elif name == "last_30_day_avg":
        start = start_of_day - timedelta(days=30)
    elif name == "weekly_avg":
        # Upstream: date_sub(data_time, interval weekday(data_time) day) keeps the clock time.
        start = moment - timedelta(days=moment.weekday())
    else:
        start = start_of_day.replace(day=1)

    values = [ _d(val) for ts, val in (history or []) if ts is not None and start <= ts < next_day ]
    if not values:
        return Decimal("0")
    avg = sum(values, Decimal("0")) / Decimal(len(values))
    return avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
