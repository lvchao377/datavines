import { Alert, Table } from "antd";
import { useEffect, useState } from "react";
import http from "../api";

export default function TokenPage() {
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  useEffect(() => { http.get("/token/page").then((data) => setRows(Array.isArray(data) ? data : [])); }, []);
  return (
    <div>
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message="本系统按交付约定关闭登录、注册和权限校验。所有接口匿名可访问，界面直接进入主页，默认用户是 admin。" />
      <Table rowKey={(row) => row.id || row.token} dataSource={rows} columns={[
        { title: "令牌", dataIndex: "token" },
        { title: "说明", dataIndex: "note" },
        { title: "过期", dataIndex: "expireTime" },
      ]} />
    </div>
  );
}
