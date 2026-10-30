"""Build metric SQL the way DataVines local/JDBC scripts do.

Templates for expected-value averages are copied from
datavines-connector-api MetricScript so tests can lock the upstream text.
Actual execution SQL is fully rendered (identifiers quoted) for MySQL/Doris.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.metrics.registry import MetricDef, get_metric

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMP = {
    "eq": "=",
    "=": "=",
    "lt": "<",
    "<": "<",
    "lte": "<=",
    "<=": "<=",
    "gt": ">",
    ">": ">",
    "gte": ">=",
    ">=": ">=",
    "neq": "!=",
    "!=": "!=",
    "<>": "<>",
    "ne": "!=",
}

# Upstream MetricScript expected-value SQL (placeholders kept).
EXPECTED_SQL = {
    "daily_avg": (
        "select round(avg(actual_value),2) as expected_value_${unique_key}"
        " from dv_actual_values where data_time >=date_format(${data_time},'%Y-%m-%d')"
        " and data_time < date_add(date_format(${data_time},'%Y-%m-%d'), interval 1 DAY)"
        " and unique_code = ${unique_code}"
    ),
    "last_7_day_avg": (
        "select round(avg(actual_value),2) as expected_value_${unique_key}"
        " from dv_actual_values where data_time >= date_sub(date_format(${data_time},'%Y-%m-%d'),interval 7 DAY)"
        " and data_time < date_add(date_format(${data_time},'%Y-%m-%d'),interval 1 DAY) and unique_code = ${unique_code}"
    ),
    "last_30_day_avg": (
        "select round(avg(actual_value),2) as expected_value_${unique_key}"
        " from dv_actual_values where data_time >= date_sub(date_format(${data_time},'%Y-%m-%d'),interval 30 DAY)"
        " and data_time < date_add(date_format(${data_time},'%Y-%m-%d'),interval 1 DAY) and unique_code = ${unique_code}"
    ),
    "monthly_avg": (
        "select round(avg(actual_value),2) as expected_value_${unique_key}"
        " from dv_actual_values where data_time >= date_format(curdate(), '%Y-%m-01') and data_time < date_add(date_format(${data_time},'%Y-%m-%d'),interval 1 DAY)"
        " and unique_code = ${unique_code}"
    ),
    "weekly_avg": (
        "select round(avg(actual_value),2) as expected_value_${unique_key}"
        " from dv_actual_values where data_time >= date_sub(${data_time},interval weekday(${data_time}) + 0 day)"
        " and data_time < date_add(date_format(${data_time},'%Y-%m-%d'),interval 1 DAY) and unique_code = ${unique_code}"
    ),
    "table_total_rows": "select count(1) as expected_value_${unique_key} from ${table}",
    "target_table_total_rows": "select count(1) as expected_value_${unique_key} from ${table2}",
}


@dataclass
class SqlPlan:
    metric: str
    actual_sql: str
    invalidate_sql: str | None = None
    expected_sql: str | None = None
    list_metric: bool = False
    error_output: bool = False
    tables: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "metric": self.metric,
            "actualSql": self.actual_sql,
            "invalidateSql": self.invalidate_sql,
            "expectedSql": self.expected_sql,
            "listMetric": self.list_metric,
            "errorOutput": self.error_output,
            "notes": self.notes,
        }


def expected_sql_template(kind: str, unique_key: str = "k") -> str | None:
    tpl = EXPECTED_SQL.get(kind)
    if tpl is None:
        return None
    return tpl.replace("${unique_key}", unique_key)


def quote_ident(name: str) -> str:
    if name is None or not _IDENT.match(str(name)):
        raise ValueError(f"非法标识符: {name}")
    return f"`{name}`"


def table_ref(database: str | None, table: str) -> str:
    if not table:
        raise ValueError("表名不能为空")
    if "." in table and not database:
        db, tbl = table.split(".", 1)
        return f"{quote_ident(db)}.{quote_ident(tbl)}"
    if database:
        return f"{quote_ident(database)}.{quote_ident(table)}"
    return quote_ident(table)


def _sql_str(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def _num(value) -> str:
    try:
        return format(Decimal(str(value)), "f")
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"非法数值: {value}") from exc


def _guard_fragment(fragment: str | None, label: str) -> str:
    if fragment is None:
        return ""
    text = str(fragment).strip()
    if not text:
        return ""
    if ";" in text or "\x00" in text:
        raise ValueError(f"{label} 不允许包含分号")
    return text


def _mysql_time_format(fmt: str) -> str:
    if not fmt:
        return "%Y-%m-%d %H:%i:%s"
    if "%" in fmt:
        return fmt
    return (
        fmt.replace("yyyy", "%Y")
        .replace("MM", "%m")
        .replace("dd", "%d")
        .replace("HH", "%H")
        .replace("mm", "%i")
        .replace("ss", "%s")
    )


def _enum_list(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("枚举值列表不能为空")
    if "'" in text:
        if ";" in text:
            raise ValueError("枚举值列表不允许包含分号")
        return text
    parts = [p.strip() for p in text.split(",") if p.strip()]
    rendered = []
    for part in parts:
        try:
            rendered.append(_num(part))
        except ValueError:
            rendered.append(_sql_str(part))
    return ", ".join(rendered)


def _where(parts: list[str]) -> str:
    cleaned = [p for p in parts if p]
    if not cleaned:
        return ""
    return " where " + " and ".join(f"({p})" if not p.startswith("(") else p for p in cleaned)


def _count_wrapper(inner: str) -> str:
    return f"select count(1) as actual_value from ( {inner} ) t"


def _agg(expr: str, table: str, where: str) -> str:
    return f"select {expr} as actual_value from {table}{where}"


def build_sql(metric_name: str, params: dict | None, *, unique_key: str = "k") -> SqlPlan:
    metric: MetricDef = get_metric(metric_name)
    params = dict(params or {})
    database = (params.get("database") or params.get("schema") or params.get("schema_name") or "").strip() or None
    table_name = (params.get("table") or params.get("table_name") or "").strip()
    column = (params.get("column") or params.get("column_name") or "").strip()
    filt = _guard_fragment(params.get("filter"), "过滤条件")
    kind = metric.kind

    def col() -> str:
        if not column:
            raise ValueError(f"指标 {metric.name} 需要列名")
        return quote_ident(column)

    def tbl(name: str | None = None, db: str | None = None) -> str:
        return table_ref(db if db is not None else database, name or table_name)

    user_where = [filt] if filt else []

    if kind == "custom_aggregate":
        sql = _guard_fragment(params.get("actual_aggregate_sql"), "自定义聚合SQL")
        if not sql:
            raise ValueError("自定义聚合 SQL 不能为空")
        low = sql.lower()
        if " as actual_value" not in low:
            sql = f"select ({sql}) as actual_value" if not low.startswith("select") else sql
        return SqlPlan(metric=metric.name, actual_sql=sql, error_output=False, notes=["自定义聚合 SQL 原样执行，需返回单行单列数值"])

    if kind == "custom_count":
        inner = _guard_fragment(params.get("actual_execute_sql") or params.get("invalidate_items_sql"), "错误数据SQL")
        if not inner:
            raise ValueError("自定义统计 SQL 不能为空")
        return SqlPlan(
            metric=metric.name,
            actual_sql=_count_wrapper(inner),
            invalidate_sql=inner,
            error_output=True,
        )

    if kind == "multi_accuracy":
        return _multi_accuracy(metric, params, database, table_name, filt)

    if kind == "multi_compare":
        return _multi_compare(metric, params, database, table_name, column, filt)

    if kind == "row_count":
        ref = tbl()
        where = _where(user_where)
        return SqlPlan(metric=metric.name, actual_sql=_agg("count(1)", ref, where), error_output=False, tables=[ref])

    ref = tbl()
    c = col()
    where_user = _where(user_where)

    if kind == "histogram":
        where = _where(user_where)
        sql = (
            "select concat(k, '\\001', cast(cnt as char)) as actual_value from ("
            f"select if({c} is null, 'NULL', cast({c} as char)) as k, count(1) as cnt "
            f"from {ref}{where} group by {c} order by cnt desc limit 50) T"
        )
        return SqlPlan(metric=metric.name, actual_sql=sql, list_metric=True, error_output=False, tables=[ref])

    agg_map = {
        "distinct": f"count(distinct({c}))",
        "min_length": f"min(length({c}))",
        "max_length": f"max(length({c}))",
        "avg_length": f"avg(length({c}))",
        "min": f"min({c})",
        "max": f"max({c})",
        "avg": f"avg({c})",
        "sum": f"sum({c})",
        "std_dev": f"stddev({c})",
        "variance": f"variance({c})",
    }
    if kind in agg_map:
        return SqlPlan(metric=metric.name, actual_sql=_agg(agg_map[kind], ref, where_user), error_output=False, tables=[ref])

    condition = _condition(kind, c, params)
    parts = [condition] if condition else []
    if filt:
        parts.append(filt)
    inner_where = _where(parts)
    if kind in ("unique_count", "duplicate_count"):
        having = " having count(1) = 1 " if kind == "unique_count" else f" having count({c}) > 1 "
        inner = f"select {c} from {ref}{inner_where} group by {c}{having}"
    else:
        inner = f"select * from {ref}{inner_where}"
    return SqlPlan(
        metric=metric.name,
        actual_sql=_count_wrapper(inner),
        invalidate_sql=inner,
        error_output=metric.error_output,
        tables=[ref],
    )


def _condition(kind: str, column_sql: str, params: dict) -> str:
    if kind == "null_count":
        return f"({column_sql} is null)"
    if kind == "not_null_count":
        return f"{column_sql} is not null"
    if kind == "blank_count":
        return f"({column_sql} is null or {column_sql} = '')"
    if kind == "in_enums":
        return f"({column_sql} in ( {_enum_list(str(params.get('enum_list') or ''))} ))"
    if kind == "not_in_enums":
        enums = _enum_list(str(params.get("enum_list") or ""))
        return f"({column_sql} not in ( {enums} ) or {column_sql} is null)"
    if kind == "match_regex":
        pattern = _guard_fragment(params.get("regexp"), "正则表达式")
        if not pattern:
            raise ValueError("正则表达式不能为空")
        return f"{column_sql} regexp {_sql_str(pattern)}"
    if kind == "not_match_regex":
        pattern = _guard_fragment(params.get("regexp"), "正则表达式")
        if not pattern:
            raise ValueError("正则表达式不能为空")
        return f"{column_sql} not regexp {_sql_str(pattern)}"
    if kind == "length_compare":
        comparator = _COMP.get(str(params.get("comparator") or "").strip())
        if not comparator:
            raise ValueError("长度检查需要比较符 comparator")
        length = _num(params.get("length"))
        return f"length({column_sql}) {comparator} {length}"
    if kind == "value_between":
        bits = []
        if params.get("min") not in (None, ""):
            bits.append(f"{column_sql} >= {_num(params.get('min'))}")
        if params.get("max") not in (None, ""):
            bits.append(f"{column_sql} <= {_num(params.get('max'))}")
        if not bits:
            raise ValueError("值范围检查至少需要 min 或 max")
        return " and ".join(bits)
    if kind == "freshness":
        fmt = _mysql_time_format(str(params.get("datetime_format") or "%Y-%m-%d %H:%i:%s"))
        begin = _guard_fragment(params.get("begin_time"), "开始时间")
        end = _guard_fragment(params.get("deadline_time"), "结束时间")
        if not begin or not end:
            raise ValueError("及时性检查需要 begin_time 与 deadline_time")
        fmt_sql = _sql_str(fmt)
        return (
            f"(DATE_FORMAT({column_sql}, {fmt_sql}) <= DATE_FORMAT({_sql_str(end)}, {fmt_sql})) "
            f"AND (DATE_FORMAT({column_sql}, {fmt_sql}) >= DATE_FORMAT({_sql_str(begin)}, {fmt_sql}))"
        )
    if kind in ("unique_count", "duplicate_count"):
        return ""
    raise ValueError(f"无法构造条件: {kind}")


def _multi_accuracy(metric: MetricDef, params: dict, database: str | None, table_name: str, filt: str) -> SqlPlan:
    database2 = (params.get("database2") or database or "").strip() or None
    table2 = (params.get("table2") or "").strip()
    if not table2:
        raise ValueError("跨表准确性需要目标表 table2")
    join_column = (params.get("join_column") or params.get("column") or "id").strip()
    compare_column = (params.get("compare_column") or "").strip()
    filt2 = _guard_fragment(params.get("filter2"), "目标表过滤")
    src = table_ref(database, table_name)
    tgt = table_ref(database2, table2)
    src_from = f"(select * from {src}{_where([filt])}) s" if filt else f"{src} s"
    tgt_from = f"(select * from {tgt}{_where([filt2])}) t" if filt2 else f"{tgt} t"
    jc = quote_ident(join_column)
    join_on = f"s.{jc} = t.{jc}"
    where = f"t.{jc} is null"
    if compare_column:
        cc = quote_ident(compare_column)
        where = f"({where} or not (s.{cc} <=> t.{cc}))"
    inner = f"select s.{jc} as src_key from {src_from} left join {tgt_from} on {join_on} where {where}"
    return SqlPlan(
        metric=metric.name,
        actual_sql=_count_wrapper(inner),
        invalidate_sql=inner,
        error_output=True,
        tables=[src, tgt],
        notes=["实际值为源表无法在目标表按关联键匹配、或比对列不一致的行数"],
    )


def _multi_compare(metric: MetricDef, params: dict, database: str | None, table_name: str, column: str, filt: str) -> SqlPlan:
    database2 = (params.get("database2") or database or "").strip() or None
    table2 = (params.get("table2") or "").strip()
    if not table2:
        raise ValueError("两表值比对需要目标表 table2")
    fn = (params.get("compare_metric") or "count").strip().lower()
    allowed = {"count", "sum", "avg", "min", "max", "table_row_count"}
    if fn not in allowed:
        raise ValueError(f"compare_metric 仅支持 {sorted(allowed)}")
    column2 = (params.get("column2") or column or "").strip()
    filt2 = _guard_fragment(params.get("filter2"), "目标表过滤")
    src = table_ref(database, table_name)
    tgt = table_ref(database2, table2)

    def expr(fn_name: str, col_name: str) -> str:
        if fn_name in ("count", "table_row_count"):
            return "count(1)"
        if not col_name:
            raise ValueError(f"{fn_name} 比对需要列名")
        quoted = quote_ident(col_name)
        return f"{fn_name}({quoted})"

    actual = _agg(expr(fn, column), src, _where([filt] if filt else []))
    expected = _agg(expr(fn, column2), tgt, _where([filt2] if filt2 else []))
    return SqlPlan(
        metric=metric.name,
        actual_sql=actual,
        expected_sql=expected,
        error_output=False,
        tables=[src, tgt],
        notes=["实际值取源表聚合，期望值取目标表同名聚合，再套用结果公式"],
    )
