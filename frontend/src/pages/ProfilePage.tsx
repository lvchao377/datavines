import { Button, Card, Col, Row, Select, Space, Statistic, message } from "antd";
import ReactECharts from "echarts-for-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import http from "../api";

export default function ProfilePage() {
  const { id } = useParams();
  const [databases, setDatabases] = useState<Record<string, any>[]>([]);
  const [database, setDatabase] = useState<string>();
  const [tables, setTables] = useState<Record<string, any>[]>([]);
  const [table, setTable] = useState<string>();
  const [entity, setEntity] = useState<Record<string, any> | null>(null);
  const [trend, setTrend] = useState<{ date: string; value: string }[]>([]);
  const [columns, setColumns] = useState<Record<string, any>[]>([]);

  useEffect(() => {
    http.get(`/catalog/databases/${id}`).then((rows) => {
      setDatabases(rows || []);
      if (rows?.[0]) setDatabase(rows[0].fullyQualifiedName);
    });
  }, [id]);

  useEffect(() => {
    const db = databases.find((item) => item.fullyQualifiedName === database);
    if (!db) return;
    http.get(`/catalog/list/table/${db.uuid}`).then(setTables);
  }, [database, databases]);

  const loadProfile = async (tableRow: Record<string, any>) => {
    setEntity(tableRow);
    setTrend(await http.get("/catalog/profile/table/records", { params: { uuid: tableRow.uuid, metric: "table_row_count" } }));
    const cols = await http.get(`/catalog/list/column/${tableRow.uuid}`);
    const detailed = await Promise.all(cols.map(async (col: Record<string, any>) => ({ ...col, metrics: await http.get(`/catalog/profile/column/${col.uuid}`) })));
    setColumns(detailed);
  };

  const run = async () => {
    if (!database || !table) return;
    const body = await http.post("/catalog/profile/execute", { datasourceId: Number(id), database, table });
    message.success(`探查已提交 #${body.taskId}，几秒后点「查看」`);
  };

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Select style={{ width: 160 }} value={database} onChange={setDatabase} options={databases.map((item) => ({ value: item.fullyQualifiedName, label: item.displayName }))} />
        <Select style={{ width: 220 }} value={table} onChange={setTable} options={tables.map((item) => ({ value: item.displayName, label: item.displayName }))} />
        <Button type="primary" onClick={run}>运行探查</Button>
        <Button onClick={() => { const row = tables.find((item) => item.displayName === table); if (row) loadProfile(row); }}>查看结果</Button>
      </Space>
      {entity && (
        <Card title={`${entity.fullyQualifiedName} 行数趋势`}>
          {trend.length === 0 ? "还没有探查记录" : (
            <ReactECharts style={{ height: 240 }} option={{
              xAxis: { type: "category", data: trend.map((item) => item.date) },
              yAxis: { type: "value" },
              series: [{ type: "bar", data: trend.map((item) => Number(item.value)) }],
              tooltip: { trigger: "axis" },
            }} />
          )}
        </Card>
      )}
      <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
        {columns.map((col) => {
          const histogram = (col.metrics || []).find((item: any) => item.metricName === "column_histogram");
          const numbers = (col.metrics || []).filter((item: any) => item.metricName !== "column_histogram");
          const histData = Array.isArray(histogram?.actualValue) ? histogram.actualValue : [];
          return (
            <Col span={12} key={col.uuid}>
              <Card title={`${col.displayName} · ${col.properties?.dataType || ""}`} size="small">
                <Row gutter={8}>
                  {numbers.map((item: any) => (
                    <Col span={8} key={item.id}><Statistic title={item.metricName} value={item.actualValue} valueStyle={{ fontSize: 16 }} /></Col>
                  ))}
                </Row>
                {histData.length > 0 && (
                  <ReactECharts style={{ height: 180 }} option={{
                    tooltip: {},
                    xAxis: { type: "category", data: histData.map((item: any) => item.key), axisLabel: { rotate: 30 } },
                    yAxis: { type: "value" },
                    series: [{ type: "bar", data: histData.map((item: any) => item.count) }],
                  }} />
                )}
              </Card>
            </Col>
          );
        })}
      </Row>
    </div>
  );
}
