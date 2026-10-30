import { Alert, Table } from "antd";
import { useEffect, useState } from "react";
import http from "../api";

export default function TokenPage() {
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  useEffect(() => { http.get("/token/page").then((data) => setRows(Array.isArray(data) ? data : [])); }, []);
  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message="登录后请求头携带 JWT。指标目录（28 条规则）不需要登录。数据源列表只返回当前用户所属工作空间的记录。" />
      <Table rowKey={(row) => row.id || row.token} dataSource={rows} columns={[
        { title: "令牌", dataIndex: "token" },
        { title: "说明", dataIndex: "note" },
        { title: "过期", dataIndex: "expireTime" },
      ]} />
    </div>
  );
}
