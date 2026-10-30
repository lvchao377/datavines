import { Button, Card, Descriptions, Space, Table, Tag } from "antd";
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import http, { STATUS } from "../api";

export default function ExecutionPage({ mode }: { mode: "list" | "log" }) {
  const { id } = useParams();
  const [params] = useSearchParams();
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [current, setCurrent] = useState<number | null>(params.get("executionId") ? Number(params.get("executionId")) : null);
  const [log, setLog] = useState("");
  const [status, setStatus] = useState<number | null>(null);
  const [results, setResults] = useState<Record<string, any>[]>([]);
  const [errors, setErrors] = useState<Record<string, any>[]>([]);

  const loadList = () => http.post("/job/execution/page", { datasourceId: Number(id), pageNumber: 1, pageSize: 50 }).then((page) => setRows(page.records || []));

  const loadDetail = async (executionId: number) => {
    const [logBody, resultBody, errorBody, statusBody] = await Promise.all([
      http.get(`/job/execution/log/${executionId}`),
      http.get(`/job/execution/list/result/${executionId}`),
      http.get("/job/execution/errorDataPage", { params: { executionId, pageNumber: 1, pageSize: 50 } }),
      http.get(`/job/execution/status/${executionId}`),
    ]);
    setLog(logBody.log || "");
    setResults(resultBody || []);
    setErrors(errorBody.records || []);
    setStatus(statusBody.status);
    return statusBody.status as number;
  };

  useEffect(() => { loadList(); }, [id]);
  useEffect(() => {
    if (!current) return;
    let stop = false;
    const tick = async () => {
      const next = await loadDetail(current);
      if (next === 6 || next === 7 || next === 9) stop = true;
    };
    tick();
    const timer = window.setInterval(() => {
      if (!stop) tick();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [current]);

  return (
    <div>
      <Table
        rowKey="id"
        dataSource={rows}
        pagination={false}
        onRow={(row) => ({ onClick: () => setCurrent(row.id) })}
        columns={[
          { title: "实例", dataIndex: "id" },
          { title: "名称", dataIndex: "name" },
          { title: "指标", dataIndex: "metricType" },
          { title: "状态", dataIndex: "status", render: (value: number) => <Tag color={STATUS[value]?.color}>{STATUS[value]?.text || value}</Tag> },
          { title: "开始", dataIndex: "startTime" },
          { title: "结束", dataIndex: "endTime" },
          { title: "操作", render: (_, row) => (row.status === 0 || row.status === 1) ? <a onClick={(event) => { event.stopPropagation(); http.delete(`/job/execution/kill/${row.id}`); }}>终止</a> : null },
        ]}
      />
      {mode === "log" && current && (
        <Card style={{ marginTop: 16 }} title={<Space>执行 #{current} {status != null && <Tag color={STATUS[status]?.color}>{STATUS[status]?.text}</Tag>} <Button size="small" onClick={() => loadDetail(current)}>刷新</Button></Space>}>
          <div className="log-box">{log || "日志还没写出来"}</div>
          <Descriptions bordered size="small" column={2} style={{ marginTop: 12 }}>
            {results.map((item) => (
              <Descriptions.Item key={item.id} label={item.metricName} span={2}>
                实际值 {item.actualValue} / 期望值 {item.expectedValue} / 公式 {item.resultFormula} / {item.operator} {item.threshold} / 分数 {item.score} / {item.state === 1 ? "通过" : "未通过"}
              </Descriptions.Item>
            ))}
          </Descriptions>
          <Table
            style={{ marginTop: 12 }}
            rowKey="id"
            size="small"
            pagination={false}
            dataSource={errors}
            locale={{ emptyText: "没有错误样本" }}
            columns={[{ title: "错误行", dataIndex: "rowData", render: (value) => <pre style={{ margin: 0 }}>{JSON.stringify(value, null, 2)}</pre> }]}
          />
        </Card>
      )}
    </div>
  );
}
