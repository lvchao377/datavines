import { DatabaseOutlined, FormOutlined, SafetyCertificateOutlined, TagOutlined, WarningOutlined, CloseCircleOutlined, CloudServerOutlined, TeamOutlined, LogoutOutlined } from "@ant-design/icons";
import { Avatar, Button, Layout, Menu, Select, Tag } from "antd";
import { useEffect, useState } from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import http from "../api";
import { logout, readUser, selectWorkspace, workspaceId } from "../session";

const { Sider, Header, Content } = Layout;

const items = [
  { key: "/main/home", icon: <DatabaseOutlined />, label: "数据源" },
  { key: "/main/warning", icon: <WarningOutlined />, label: "告警管理" },
  { key: "/main/errorDataManage", icon: <CloseCircleOutlined />, label: "错误数据存储" },
  { key: "/main/label", icon: <TagOutlined />, label: "标签管理" },
  { key: "/main/config", icon: <FormOutlined />, label: "参数配置" },
  { key: "/main/env", icon: <CloudServerOutlined />, label: "运行环境" },
  { key: "/main/tokenManager", icon: <SafetyCertificateOutlined />, label: "令牌" },
  { key: "/main/users", icon: <TeamOutlined />, label: "用户" },
];

export default function MainLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const [healthy, setHealthy] = useState<boolean | null>(null);
  const [spaces, setSpaces] = useState<{ id: number; name: string }[]>([]);
  const [currentWorkspace, setCurrentWorkspace] = useState(workspaceId() || undefined);
  const user = readUser();
  const selected = items.find((item) => location.pathname.startsWith(item.key))?.key || "/main/home";

  useEffect(() => {
    http.get("/health").then(() => setHealthy(true)).catch(() => setHealthy(false));
    http.get("/workspace/list").then((rows: { id: number; name: string }[]) => {
      setSpaces(rows || []);
      if (!workspaceId() && rows?.[0]) {
        selectWorkspace(rows[0].id);
        setCurrentWorkspace(String(rows[0].id));
      }
    });
  }, []);

  const signOut = () => {
    logout();
    navigate("/login");
  };

  return (
    <Layout style={{ minHeight: "100%" }}>
      <Sider width={216} theme="dark" style={{ background: "#0b1f33" }}>
        <div className="dv-logo">Data<span>Vines</span></div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          items={items}
          style={{ background: "#0b1f33" }}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header className="dv-header">
          <Select
            style={{ minWidth: 220 }}
            placeholder="工作空间"
            value={currentWorkspace}
            options={spaces.map((item) => ({ value: String(item.id), label: item.name }))}
            onChange={(value) => {
              setCurrentWorkspace(value);
              selectWorkspace(value);
              navigate("/main/home");
            }}
          />
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Tag color={healthy ? "success" : healthy === false ? "error" : "default"}>{healthy ? "服务正常" : healthy === false ? "服务不可用" : "检查中"}</Tag>
            <Avatar size="small" style={{ background: "#1677ff" }}>{(user?.username || "?").slice(0, 1).toUpperCase()}</Avatar>
            <span>{user?.username || "未登录"}</span>
            <Button type="text" icon={<LogoutOutlined />} onClick={signOut}>退出</Button>
          </div>
        </Header>
        <Content className="dv-content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
