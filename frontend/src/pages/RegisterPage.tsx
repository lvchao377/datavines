import { LockOutlined, MailOutlined, UserOutlined } from "@ant-design/icons";
import { Button, Card, Form, Input } from "antd";
import { Link, useNavigate } from "react-router-dom";
import http from "../api";

export default function RegisterPage() {
  const navigate = useNavigate();

  const submit = async (values: { username: string; email: string; password: string }) => {
    await http.post("/register", values);
    navigate("/login");
  };

  return (
    <div className="auth-page">
      <Card className="auth-card" bordered={false}>
        <div className="auth-brand">Data<span>Vines</span></div>
        <Form layout="vertical" onFinish={submit} requiredMark={false}>
          <Form.Item name="username" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input size="large" prefix={<UserOutlined />} placeholder="用户名" autoComplete="username" />
          </Form.Item>
          <Form.Item name="email" rules={[{ required: true, type: "email", message: "请输入邮箱" }]}>
            <Input size="large" prefix={<MailOutlined />} placeholder="邮箱" autoComplete="email" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, min: 6, message: "密码至少 6 位" }]}>
            <Input.Password size="large" prefix={<LockOutlined />} placeholder="密码" autoComplete="new-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" size="large" block>注册</Button>
        </Form>
        <div className="auth-extra">已有账号？<Link to="/login">登录</Link></div>
      </Card>
    </div>
  );
}
