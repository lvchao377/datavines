import { PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { Button, Card, Empty, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Tag, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import http from "../api";

type DataSource = {
  id: number;
  name: string;
  type: string;
  param?: { host?: string; port?: number; database?: string; user?: string };
};

export default function HomePage() {
  const navigate = useNavigate();
  const [rows, setRows] = useState<DataSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [types, setTypes] = useState<{ value: string; label: string; supported: boolean; defaultPort?: number }[]>([]);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const page = await http.get("/datasource/page", { params: { pageNumber: 1, pageSize: 100 } });
      setRows(page.records || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    http.get("/datasource/type/list").then(setTypes);
  }, []);

  const create = async () => {
    const values = await form.validateFields();
    await http.post("/datasource", {
      name: values.name,
      type: values.type,
      param: { host: values.host, port: values.port, database: values.database, user: values.user, password: values.password || "" },
    });
    message.success("数据源已创建");
    setOpen(false);
    form.resetFields();
    load();
  };

  const test = async (id: number) => {
    const detail = await http.get(`/datasource/${id}`);
    await http.post("/datasource/test", { type: detail.type, param: detail.param });
    message.success("连接成功");
  };

  const bootstrap = async () => {
    const data = await http.post("/demo/bootstrap");
    message.success(`Demo 已就绪，数据源 #${data.datasourceId}`);
    load();
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>数据源</Typography.Title>
          <Typography.Text type="secondary">检查 MySQL 或 Doris。其他类型仅作占位，不能保存。</Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button onClick={bootstrap}>初始化 Demo</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { form.setFieldsValue({ type: "mysql", port: 3306 }); setOpen(true); }}>新建数据源</Button>
        </Space>
      </div>
      {rows.length === 0 && !loading ? (
        <Card><Empty description="还没有数据源。可以初始化内置 Demo，或手工登记一套 MySQL。"><Button type="primary" onClick={bootstrap}>初始化 Demo</Button></Empty></Card>
      ) : (
        <div className="ds-grid">
          {rows.map((row) => (
            <Card
              key={row.id}
              className="ds-card"
              loading={loading}
              title={row.name}
              extra={<Tag color={row.type === "doris" ? "purple" : "blue"}>{row.type}</Tag>}
              actions={[
                <a key="enter" onClick={() => navigate(`/main/detail/${row.id}/dashboard`)}>进入</a>,
                <a key="test" onClick={() => test(row.id)}>测试连接</a>,
                <Popconfirm key="del" title="删除该数据源？" onConfirm={async () => { await http.delete(`/datasource/${row.id}`); load(); }}>
                  <a>删除</a>
                </Popconfirm>,
              ]}
            >
              <div>{row.param?.host}:{row.param?.port}</div>
              <Typography.Text type="secondary">{row.param?.database || "未指定默认库"} · {row.param?.user}</Typography.Text>
            </Card>
          ))}
        </div>
      )}
      <Modal title="新建数据源" open={open} onCancel={() => setOpen(false)} onOk={create} okText="保存">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input placeholder="订单库" /></Form.Item>
          <Form.Item name="type" label="类型" rules={[{ required: true }]}>
            <Select
              options={types.map((item) => ({ value: item.value, label: item.supported ? item.label : `${item.label}（未实现）`, disabled: !item.supported }))}
              onChange={(value) => {
                const found = types.find((item) => item.value === value);
                if (found?.defaultPort) form.setFieldValue("port", found.defaultPort);
              }}
            />
          </Form.Item>
          <Form.Item name="host" label="主机" rules={[{ required: true }]}><Input placeholder="127.0.0.1 或 mysql" /></Form.Item>
          <Form.Item name="port" label="端口" rules={[{ required: true }]}><InputNumber style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="database" label="数据库"><Input placeholder="可留空，进入后浏览全部库" /></Form.Item>
          <Form.Item name="user" label="用户名" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="password" label="密码"><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
