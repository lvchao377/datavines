import re
from pathlib import Path

from app import models


def _upstream_columns() -> dict[str, list[str]]:
    path = Path(__file__).resolve().parents[2] / "scripts" / "sql" / "datavines-mysql.sql"
    sql = path.read_text(encoding="utf-8")
    found = {}
    for part in re.split(r"CREATE TABLE `", sql)[1:]:
        name = part.split("`", 1)[0]
        if not name.startswith("dv_"):
            continue
        body = part.split(") ENGINE", 1)[0]
        cols = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            match = re.match(r"`(\w+)`\s+[a-zA-Z]+", line)
            if match:
                cols.append(match.group(1))
        found[name] = cols
    return found


def test_models_cover_upstream_dv_columns():
    upstream = _upstream_columns()
    assert len(upstream) >= 36
    by_name = {table.name: table for table in models.Base.metadata.tables.values()}
    missing_tables = []
    missing_columns = []
    for name, columns in upstream.items():
        table = by_name.get(name)
        if table is None:
            missing_tables.append(name)
            continue
        have = set(table.columns.keys())
        for column in columns:
            if column not in have:
                missing_columns.append(f"{name}.{column}")
    assert missing_tables == []
    assert missing_columns == []
