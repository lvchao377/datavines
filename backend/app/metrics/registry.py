"""Upstream metric plugin names, dimensions and config keys.

Names and Chinese labels follow datavines-metric-plugins on the dev branch.
column_histogram is registered but excluded from the quality-job dropdown,
matching MetricController.excludeMetricSet.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MetricDef:
    name: str
    zh_name: str
    dimension: str
    metric_type: str  # SINGLE_TABLE | MULTI_TABLE_ACCURACY | MULTI_TABLE_VALUE_COMPARISON
    level: str  # column | table | none
    direction: str  # POSITIVE | NEGATIVE
    kind: str
    error_output: bool = False
    configs: list[dict] = field(default_factory=list)
    aliases: tuple[str, ...] = ()
    exclude_from_quality_list: bool = False

    @property
    def single_table(self) -> bool:
        return self.metric_type == "SINGLE_TABLE"


def _col(extra: list[dict] | None = None) -> list[dict]:
    items = [
        {"key": "column", "label": "列名", "supportMultiple": False},
        {"key": "filter", "label": "过滤条件", "supportMultiple": False},
    ]
    if extra:
        items.extend(extra)
    return items


ENUM = [{"key": "enum_list", "label": "枚举值列表", "supportMultiple": False}]
REGEX = [{"key": "regexp", "label": "正则表达式", "supportMultiple": False}]
LENGTH = [
    {"key": "comparator", "label": "比较符", "supportMultiple": False},
    {"key": "length", "label": "长度", "supportMultiple": False},
]
BETWEEN = [
    {"key": "min", "label": "最小值", "supportMultiple": False},
    {"key": "max", "label": "最大值", "supportMultiple": False},
]
FRESH = [
    {"key": "begin_time", "label": "开始时间", "supportMultiple": False},
    {"key": "deadline_time", "label": "结束时间", "supportMultiple": False},
    {"key": "datetime_format", "label": "时间格式", "supportMultiple": False},
]


def _m(**kwargs) -> MetricDef:
    return MetricDef(**kwargs)


_RAW: list[MetricDef] = [
    _m(name="column_null", zh_name="空值检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="NEGATIVE", kind="null_count", error_output=True, configs=_col()),
    _m(name="column_not_null", zh_name="非空检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="not_null_count", error_output=True, configs=_col()),
    _m(name="column_blank", zh_name="无值检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="NEGATIVE", kind="blank_count", error_output=True, configs=_col()),
    _m(name="column_unique", zh_name="唯一性检查", dimension="UNIQUENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="unique_count", error_output=True, configs=_col()),
    _m(name="column_distinct", zh_name="Distinct检查", dimension="UNIQUENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="distinct", error_output=False, configs=_col()),
    _m(name="column_duplicate", zh_name="重复值检查", dimension="UNIQUENESS", metric_type="SINGLE_TABLE", level="column", direction="NEGATIVE", kind="duplicate_count", error_output=True, configs=_col()),
    _m(name="column_in_enums", zh_name="枚举值检查", dimension="EFFECTIVENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="in_enums", error_output=True, configs=_col(ENUM)),
    _m(name="column_not_in_enums", zh_name="枚举值[不在]检查", dimension="EFFECTIVENESS", metric_type="SINGLE_TABLE", level="column", direction="NEGATIVE", kind="not_in_enums", error_output=True, configs=_col(ENUM)),
    _m(name="column_match_regex", zh_name="正则表达式[匹配]检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="match_regex", error_output=True, configs=_col(REGEX)),
    _m(name="column_match_not_regex", zh_name="正则表达式[不匹配]检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="NEGATIVE", kind="not_match_regex", error_output=True, configs=_col(REGEX)),
    _m(name="column_value_between", zh_name="值范围检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="value_between", error_output=True, configs=_col(BETWEEN)),
    _m(name="column_length", zh_name="长度检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="length_compare", error_output=True, configs=_col(LENGTH)),
    _m(name="column_min_length", zh_name="字段最小长度检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="min_length", error_output=False, configs=_col()),
    _m(name="column_max_length", zh_name="字段最大长度检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="max_length", error_output=False, configs=_col()),
    _m(name="column_avg_length", zh_name="字段平均长度检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="avg_length", error_output=False, configs=_col()),
    _m(name="column_min", zh_name="最小值检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="min", error_output=False, configs=_col()),
    _m(name="column_max", zh_name="最大值检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="max", error_output=False, configs=_col()),
    _m(name="column_avg", zh_name="平均值检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="avg", error_output=False, configs=_col()),
    _m(name="column_sum", zh_name="总值检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="sum", error_output=False, configs=_col()),
    _m(name="column_std_dev", zh_name="标准差检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="std_dev", error_output=False, configs=_col()),
    _m(name="column_variance", zh_name="方差检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="variance", error_output=False, configs=_col()),
    _m(name="column_histogram", zh_name="数据分布检查", dimension="COMPLETENESS", metric_type="SINGLE_TABLE", level="column", direction="POSITIVE", kind="histogram", error_output=False, configs=_col(), exclude_from_quality_list=True),
    _m(
        name="table_row_count",
        zh_name="表行数检查",
        dimension="COMPLETENESS",
        metric_type="SINGLE_TABLE",
        level="table",
        direction="POSITIVE",
        kind="row_count",
        error_output=False,
        configs=[{"key": "table", "label": "表名", "supportMultiple": True}, {"key": "filter", "label": "过滤条件", "supportMultiple": False}],
    ),
    _m(
        name="freshness",
        zh_name="及时性检查",
        dimension="TIMELINESS",
        metric_type="SINGLE_TABLE",
        level="column",
        direction="POSITIVE",
        kind="freshness",
        error_output=True,
        configs=_col(FRESH),
        aliases=("table_freshness",),
    ),
    _m(
        name="custom_aggregate_sql",
        zh_name="自定义聚合SQL",
        dimension="ACCURACY",
        metric_type="SINGLE_TABLE",
        level="none",
        direction="POSITIVE",
        kind="custom_aggregate",
        error_output=False,
        configs=[{"key": "actual_aggregate_sql", "label": "自定义聚合SQL", "supportMultiple": False}],
    ),
    _m(
        name="custom_count_sql",
        zh_name="自定义统计SQL",
        dimension="ACCURACY",
        metric_type="SINGLE_TABLE",
        level="none",
        direction="POSITIVE",
        kind="custom_count",
        error_output=True,
        configs=[{"key": "actual_execute_sql", "label": "错误数据SQL", "supportMultiple": False}],
    ),
    _m(
        name="multi_table_accuracy",
        zh_name="跨表准确性检查",
        dimension="ACCURACY",
        metric_type="MULTI_TABLE_ACCURACY",
        level="none",
        direction="NEGATIVE",
        kind="multi_accuracy",
        error_output=True,
        configs=[
            {"key": "table2", "label": "目标表", "supportMultiple": False},
            {"key": "filter", "label": "源表过滤", "supportMultiple": False},
            {"key": "filter2", "label": "目标表过滤", "supportMultiple": False},
            {"key": "join_column", "label": "关联列", "supportMultiple": False},
            {"key": "compare_column", "label": "比对列", "supportMultiple": False},
        ],
    ),
    _m(
        name="multi_table_value_comparison",
        zh_name="两表值比对",
        dimension="ACCURACY",
        metric_type="MULTI_TABLE_VALUE_COMPARISON",
        level="none",
        direction="POSITIVE",
        kind="multi_compare",
        error_output=False,
        configs=[
            {"key": "table2", "label": "目标表", "supportMultiple": False},
            {"key": "column", "label": "源列", "supportMultiple": False},
            {"key": "column2", "label": "目标列", "supportMultiple": False},
            {"key": "compare_metric", "label": "比对聚合", "supportMultiple": False},
            {"key": "filter", "label": "源表过滤", "supportMultiple": False},
            {"key": "filter2", "label": "目标表过滤", "supportMultiple": False},
        ],
    ),
]

METRICS: dict[str, MetricDef] = {}
for _item in _RAW:
    METRICS[_item.name] = _item
    for _alias in _item.aliases:
        METRICS[_alias] = _item


def get_metric(name: str) -> MetricDef:
    key = (name or "").strip()
    if key not in METRICS:
        raise KeyError(f"未知指标: {name}")
    return METRICS[key]


def list_metrics() -> list[MetricDef]:
    seen: set[str] = set()
    out: list[MetricDef] = []
    for item in _RAW:
        if item.name not in seen:
            seen.add(item.name)
            out.append(item)
    return out
