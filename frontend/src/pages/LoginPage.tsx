import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { Button, Card, Form, Input, Typography } from "antd";
import { Link, Navigate, useNavigate } from "react-router-dom";
import http from "../api";
import { readToken, saveSession } from "../session";

export default function LoginPage() {
  const navigate = useNavigate();
  if (readToken()) return <Navigate to="/main/home" replace />;

  const submit = async (values: { username: string; password: string }) => {
    const data = await http.post("/login", values);
    saveSession(data);
    navigate("/main/home");
  };

  return (
    <div className="auth-page">
      <Card className="auth-card" bordered={false}>
        <div className="auth-brand">Data<span>Vines</span></div>
        <Typography.Paragraph type="secondary">使用账号登录。预置账号 admin / 123456 与 user / 123456。</Typography.Paragraph>
        <Form layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input size="large" prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password size="large" prefix={<LockOutlined />} placeholder="密码" autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block>登录</Button>
        </Form>
        <div className="auth-extra">还没有账号？<Link to="/register">注册</Link></div>
      </Card>
    </div>
  );
}
