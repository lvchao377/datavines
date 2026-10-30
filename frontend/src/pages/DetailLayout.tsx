import { ArrowLeftOutlined } from "@ant-design/icons";
import { Button, Menu, Space, Spin, Typography } from "antd";
import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import http from "../api";

const tabs = [
  { key: "dashboard", label: "质量概览" },
  { key: "editor", label: "规则作业" },
  { key: "jobs", label: "执行记录" },
  { key: "jobExecutionLogs", label: "执行日志" },
  { key: "catalog", label: "数据目录" },
  { key: "profile", label: "数据概览" },
  { key: "schema", label: "Schema 变更" },
];

export default function DetailLayout() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [ds, setDs] = useState<{ name?: string; type?: string } | null>(null);
  const current = tabs.find((tab) => location.pathname.endsWith("/" + tab.key))?.key || "dashboard";

  useEffect(() => {
    http.get(`/datasource/${id}`).then(setDs).catch(() => setDs(null));
  }, [id]);

  if (!ds) return <Spin />;
  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate("/main/home")}>数据源</Button>
        <Typography.Title level={4} style={{ margin: 0 }}>{ds.name}</Typography.Title>
        <Typography.Text type="secondary">{ds.type}</Typography.Text>
      </Space>
      <Menu
        mode="horizontal"
        selectedKeys={[current]}
        items={tabs}
        onClick={({ key }) => navigate(`/main/detail/${id}/${key}`)}
      />
      <div style={{ marginTop: 16 }}>
        <Outlet />
      </div>
    </div>
  );
}
