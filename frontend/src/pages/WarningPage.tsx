import { Button, Card, Form, Input, Modal, Select, Space, Table, Tag, message } from "antd";
import { useEffect, useState } from "react";
import http from "../api";

export default function WarningPage() {
  const [slas, setSlas] = useState<Record<string, any>[]>([]);
  const [senders, setSenders] = useState<Record<string, any>[]>([]);
  const [jobs, setJobs] = useState<Record<string, any>[]>([]);
  const [logs, setLogs] = useState<Record<string, any>[]>([]);
  const [open, setOpen] = useState(false);
  const [senderOpen, setSenderOpen] = useState(false);
  const [form] = Form.useForm();
  const [senderForm] = Form.useForm();

  const load = async () => {
    const slaPage = await http.get("/sla/page", { params: { pageNumber: 1, pageSize: 50, workspaceId: 1 } });
    setSlas(slaPage.records || []);
    setSenders(await http.get("/sla/sender/list", { params: { workspaceId: 1 } }));
    const jobPage = await http.get("/job/page", { params: { pageNumber: 1, pageSize: 100 } });
    setJobs(jobPage.records || []);
    const inbox = await http.get("/sla/mock/messages");
    setLogs(inbox.logs || []);
  };
  useEffect(() => { load(); }, []);

  return (
    <div>
      <Space style={{ marginBottom: 12 }}>
        <Button type="primary" onClick={() => setOpen(true)}>新建 SLA</Button>
        <Button onClick={() => setSenderOpen(true)}>新建飞书发送器</Button>
        <Button onClick={load}>刷新</Button>
      </Space>
      <Card title="SLA">
        <Table rowKey="id" dataSource={slas} columns={[
          { title: "名称", dataIndex: "name" },
          { title: "说明", dataIndex: "description" },
          { title: "操作", render: (_, row) => <a onClick={async () => { const result = await http.get(`/sla/test/${row.id}`); message.info(JSON.stringify(result)); load(); }}>发送测试</a> },
        ]} />
      </Card>
      <Card title="飞书发送器" style={{ marginTop: 16 }}>
        <Table rowKey="id" dataSource={senders} columns={[
          { title: "名称", dataIndex: "name" },
          { title: "类型", dataIndex: "type", render: (value: string) => <Tag color="blue">{value}</Tag> },
          { title: "Webhook", render: (_, row) => row.config?.webhook },
          { title: "操作", render: (_, row) => <a onClick={async () => { await http.post("/sla/sender/test", { id: row.id }); message.success("已发送"); load(); }}>测试</a> },
        ]} />
      </Card>
      <Card title="发送记录" style={{ marginTop: 16 }}>
        <Table rowKey="id" dataSource={logs} columns={[
          { title: "标题", dataIndex: "title" },
          { title: "成功", dataIndex: "success", render: (value: number) => value ? "是" : "否" },
          { title: "响应", dataIndex: "responseBody", ellipsis: true },
          { title: "时间", dataIndex: "createTime" },
        ]} />
      </Card>
      <Modal title="新建 SLA 并关联作业" open={open} onCancel={() => setOpen(false)} onOk={async () => {
        const values = await form.validateFields();
        const sla = await http.post("/sla", { name: values.name, description: values.description || "" });
        if (values.senderId) await http.post("/sla/notification", { slaId: sla.id, senderId: values.senderId, type: "feishu" });
        if (values.jobId) await http.post("/sla/job/createOrUpdate", { slaId: sla.id, jobId: values.jobId });
        message.success("SLA 已创建");
        setOpen(false);
        load();
      }}>
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="description" label="说明"><Input /></Form.Item>
          <Form.Item name="senderId" label="飞书发送器"><Select options={senders.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
          <Form.Item name="jobId" label="关联作业"><Select options={jobs.map((item) => ({ value: item.id, label: item.name }))} /></Form.Item>
        </Form>
      </Modal>
      <Modal title="飞书 Webhook" open={senderOpen} onCancel={() => setSenderOpen(false)} onOk={async () => {
        const values = await senderForm.validateFields();
        await http.post("/sla/sender", { name: values.name, type: "feishu", config: { webhook: values.webhook } });
        message.success("发送器已保存");
        setSenderOpen(false);
        load();
      }}>
        <Form form={senderForm} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="webhook" label="Webhook" rules={[{ required: true }]} extra="内置 mock：http://127.0.0.1:5600/api/v1/sla/mock/receive">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
