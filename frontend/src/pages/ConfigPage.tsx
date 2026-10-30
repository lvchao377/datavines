import { Button, Form, Input, Modal, Table, message } from "antd";
import { useEffect, useState } from "react";
import http from "../api";

export default function ConfigPage() {
  const [rows, setRows] = useState<Record<string, any>[]>([]);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm();
  const load = () => http.get("/config/page", { params: { pageNumber: 1, pageSize: 50 } }).then((page) => setRows(page.records || []));
  useEffect(() => { load(); }, []);
  return (
    <div>
      <Button type="primary" style={{ marginBottom: 12 }} onClick={() => setOpen(true)}>新增参数</Button>
      <Table rowKey="id" dataSource={rows} columns={[
        { title: "键", dataIndex: "varKey" },
        { title: "值", dataIndex: "varValue", ellipsis: true },
        { title: "工作空间", dataIndex: "workspaceId" },
      ]} />
      <Modal title="参数" open={open} onCancel={() => setOpen(false)} onOk={async () => {
        const values = await form.validateFields();
        await http.post("/config", { varKey: values.varKey, varValue: values.varValue, workspaceId: 1 });
        message.success("已保存");
        setOpen(false);
        load();
      }}>
        <Form form={form} layout="vertical">
          <Form.Item name="varKey" label="键" rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="varValue" label="值" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
