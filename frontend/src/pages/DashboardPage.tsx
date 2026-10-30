import { Card, Col, Empty, Row, Statistic, Table, Tag } from "antd";
import ReactECharts from "echarts-for-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import http from "../api";

export default function DashboardPage() {
  const { id } = useParams();
  const [score, setScore] = useState<number | null>(null);
  const [trend, setTrend] = useState<{ date: string; score: number }[]>([]);
  const [pie, setPie] = useState<{ name: string; value: number }[]>([]);
  const [issues, setIssues] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    http.post("/job/quality-report/score", { datasourceId: Number(id), entityLevel: "DATASOURCE" }).then((row) => setScore(row?.score ?? null));
    http.post("/job/quality-report/score-trend", { datasourceId: Number(id), entityLevel: "DATASOURCE" }).then(setTrend);
    http.post("/job/execution/agg-pie", { datasourceId: Number(id) }).then(setPie);
    http.get("/catalog/page/entity/issue", { params: { datasourceId: id, pageNumber: 1, pageSize: 8 } }).then((page) => setIssues(page.records || []));
  }, [id]);

  return (
    <div>
      <Row gutter={16}>
        <Col span={6}>
          <Card>
            <Statistic title="数据源质量分" value={score ?? "—"} precision={score == null ? undefined : 2} suffix={score == null ? "" : "分"} />
          </Card>
        </Col>
        <Col span={9}>
          <Card title="通过 / 未通过">
            {pie.length === 0 ? <Empty /> : (
              <ReactECharts style={{ height: 220 }} option={{ tooltip: { trigger: "item" }, series: [{ type: "pie", radius: "70%", data: pie }] }} />
            )}
          </Card>
        </Col>
        <Col span={9}>
          <Card title="质量分趋势">
            {trend.length === 0 ? <Empty /> : (
              <ReactECharts style={{ height: 220 }} option={{
                tooltip: { trigger: "axis" },
                xAxis: { type: "category", data: trend.map((item) => item.date) },
                yAxis: { type: "value", min: 0, max: 100 },
                series: [{ type: "line", data: trend.map((item) => item.score), smooth: true, areaStyle: {} }],
              }} />
            )}
          </Card>
        </Col>
      </Row>
      <Card title="最近问题" style={{ marginTop: 16 }}>
        <Table
          rowKey="id"
          pagination={false}
          dataSource={issues}
          columns={[
            { title: "标题", dataIndex: "title" },
            { title: "状态", dataIndex: "status", render: (value: string) => <Tag color={value === "bad" ? "red" : "green"}>{value}</Tag> },
            { title: "时间", dataIndex: "createTime" },
          ]}
        />
      </Card>
    </div>
  );
}
