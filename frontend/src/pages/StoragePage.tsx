import { Button, Form, Input, InputNumber, Modal, Table, message } from "antd";
import { useEffect, useState } from "react";
import http from "../api";

export default function StoragePage() {
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const load = () => http.get("/errorDataStorage/list/1").then(setRows);
  useEffect(() => { load(); }, []);
  return (
    <div>
      <Button type="primary" style={{ marginBottom: 12 }} onClick={() => setOpen(true)}>新建 MySQL 错误存储</Button>
      <Table rowKey="id" dataSource={rows} columns={[
        { title: "名称", dataIndex: "name" },
        { title: "类型", dataIndex: "type" },
        { title: "主机", render: (_, row) => `${row.param?.host || ""}:${row.param?.port || ""}/${row.param?.database || ""}` },
        { title: "操作", render: (_, row) => <a onClick={async () => { await http.delete(`/errorDataStorage/${row.id}`); load(); }}>删除</a> },
      ]} />
      <Modal title="错误数据存储" open={open} onCancel={() => setOpen(false)} onOk={async () => {
        const values = await form.validateFields();
        const param = { host: values.host, port: values.port, database: values.database, user: values.user, password: values.password };
        await http.post("/errorDataStorage/test", { type: "mysql", param });
        await http.post("/errorDataStorage", { name: values.name, type: "mysql", param });
        message.success("已保存");
        setOpen(false);
        load();
      }}>
        <Form form={form} layout="vertical" initialValues={{ port: 3306 }}>
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="host" label="主机" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="port" label="端口"><InputNumber style={{ width: "100%" }} /></Form.Item>
          <Form.Item name="database" label="数据库" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="user" label="用户" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="password" label="密码"><Input.Password /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
