import { Button, Form, Input, Modal, Table, message } from "antd";
import { useEffect, useState } from "react";
import http from "../api";

export default function EnvPage() {
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const load = () => http.get("/env/list/1").then(setRows);
  useEffect(() => { load(); }, []);
  return (
    <div>
      <p>运行环境保存 Spark 等引擎参数。本机执行走 local，不读取这里的 Spark 配置去提交作业。</p>
      <Button type="primary" style={{ marginBottom: 12 }} onClick={() => setOpen(true)}>新建环境</Button>
      <Table rowKey="id" dataSource={rows} columns={[
        { title: "名称", dataIndex: "name" },
        { title: "配置", render: (_, row) => JSON.stringify(row.env) },
      ]} />
      <Modal title="环境" open={open} onCancel={() => setOpen(false)} onOk={async () => {
        const values = await form.validateFields();
        await http.post("/env", { name: values.name, env: { SPARK_HOME: values.sparkHome || "" }, workspaceId: 1 });
        message.success("已保存");
        setOpen(false);
        load();
      }}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="sparkHome" label="SPARK_HOME（仅记录）"><Input placeholder="/opt/spark" /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
